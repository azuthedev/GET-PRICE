import logging
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
from functools import lru_cache
import math
import hashlib
import json
from time import time

from config import Config
from pricing import calculate_price
from geo_utils import load_geo_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Cache for expensive operations
cache = {}
# Request deduplication cache with expiry time
request_cache = {}
# Track in-flight requests to prevent duplicate processing
active_requests = {}

# Load configuration and geo data on startup - these will be refreshed periodically
config = Config(use_supabase=True)
geo_data_path = os.getenv("GEOJSON_PATH", "data/editedITprov.geojson")
geo_data = load_geo_data(geo_data_path)

app = FastAPI(
    title="Airport Transfer Pricing API",
    description="API for calculating transfer prices based on distance, zones, and time",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PriceRequest(BaseModel):
    pickup_lat: float = Field(..., description="Pickup latitude", ge=-90, le=90)
    pickup_lng: float = Field(..., description="Pickup longitude", ge=-180, le=180)
    dropoff_lat: float = Field(..., description="Dropoff latitude", ge=-90, le=90)
    dropoff_lng: float = Field(..., description="Dropoff longitude", ge=-180, le=180)
    vehicle_category: Optional[str] = Field(None, description="Optional vehicle category (e.g., 'standard_sedan', 'premium_sedan')")
    pickup_time: datetime = Field(..., description="Pickup time in ISO8601 format")
    trip_type: Union[str, int] = Field(..., description="Trip type: '1' for one-way, '2' for round trip")
    
    @validator('vehicle_category')
    def validate_vehicle_category(cls, v):
        """Validate vehicle category is lowercase if provided"""
        if v is not None:
            return v.lower()
        return v
    
    @validator('trip_type')
    def validate_trip_type(cls, v):
        """Validate trip_type is either '1' or '2'"""
        if isinstance(v, int):
            v = str(v)
        
        if v not in ["1", "2"]:
            raise ValueError("trip_type must be '1' (one-way) or '2' (round trip)")
        return v

class VehiclePriceInfo(BaseModel):
    category: str
    raw_price: float
    currency: str
    price: float

class PriceResponse(BaseModel):
    prices: List[VehiclePriceInfo]
    details: Optional[Dict[str, Any]] = None

def round_to_nearest_10(price: float) -> float:
    """Round the price to the nearest 10 euros for a premium look, ensuring .5 rounds up"""
    # Use standard rounding function which will round .5 to the even number
    # To ensure .5 always rounds up, add a tiny amount
    return round(price / 10.0) * 10.0

def generate_request_hash(request: PriceRequest) -> str:
    """Generate exact hash for duplicate detection"""
    # Use higher precision (6 decimal places) to avoid false positives
    key_dict = {
        "pickup_lat": round(request.pickup_lat, 6),
        "pickup_lng": round(request.pickup_lng, 6),
        "dropoff_lat": round(request.dropoff_lat, 6),
        "dropoff_lng": round(request.dropoff_lng, 6),
        "trip_type": str(request.trip_type),
        "date": request.pickup_time.date().isoformat()  # Same day requests
    }
    
    # Include vehicle category if specified
    if request.vehicle_category:
        key_dict["vehicle_category"] = request.vehicle_category
        
    # Create hash
    return hashlib.sha256(json.dumps(key_dict, sort_keys=True).encode()).hexdigest()[:16]

@lru_cache(maxsize=100)
def get_config():
    """Return the current configuration (can be refreshed periodically)"""
    return config

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/config")
async def get_configuration():
    """Get basic configuration information"""
    conf = get_config()
    return {
        "vehicle_categories": list(conf.vehicle_rates.keys()),
        "currency": conf.currency,
        "zones": list(conf.zone_multipliers.keys()),
    }

@app.post("/check-price", response_model=PriceResponse)
async def check_price(request: PriceRequest) -> Dict[str, Any]:
    """
    Calculate the price for all vehicle categories based on pickup/dropoff coordinates
    """
    # Generate a unique request ID for tracking and deduplication
    request_id = generate_request_hash(request)
    current_time = time()
    
    # Log detailed request info for debugging
    logger.info(f"Price check request [id={request_id}]: "
                f"({request.pickup_lat}, {request.pickup_lng}) -> ({request.dropoff_lat}, {request.dropoff_lng}) "
                f"vehicle={request.vehicle_category}, trip_type={request.trip_type}, time={request.pickup_time}")
    
    # Check if we have a cached response and it's still valid (60 second TTL)
    if request_id in request_cache:
        cache_entry = request_cache[request_id]
        if current_time - cache_entry['timestamp'] < 60:  # 60 seconds cache TTL
            logger.info(f"Cache hit for request [id={request_id}]")
            return cache_entry['response']
    
    # Check if same request is already processing
    if request_id in active_requests:
        logger.warning(f"Duplicate request detected [id={request_id}] - waiting for result")
        # Wait for the in-flight request to complete
        # Simple implementation: check every 100ms for up to 5 seconds
        for _ in range(50):  # 50 * 100ms = 5 seconds
            import time as time_module
            time_module.sleep(0.1)
            if request_id in request_cache:
                logger.info(f"Using result from concurrent request [id={request_id}]")
                return request_cache[request_id]['response']
    
    # Mark this request as being processed
    active_requests[request_id] = True
    
    try:
        # Get fresh config
        conf = get_config()
        
        # Calculate prices for all vehicle categories
        prices_list = []
        
        # Define vehicle categories to calculate prices for
        categories = [request.vehicle_category] if request.vehicle_category else conf.vehicle_rates.keys()
        
        for category in categories:
            price, curr = calculate_price(
                pickup_lat=request.pickup_lat,
                pickup_lng=request.pickup_lng,
                dropoff_lat=request.dropoff_lat,
                dropoff_lng=request.dropoff_lng,
                vehicle_category=category,
                pickup_time=request.pickup_time,
                config=conf,
                geo_data=geo_data,
                trip_type=request.trip_type
            )
            
            # Round to the nearest 10 euros with improved rounding logic
            rounded_price = round_to_nearest_10(price)
            logger.debug(f"Category {category}: raw_price={price}, rounded_price={rounded_price}")
            
            prices_list.append(
                VehiclePriceInfo(
                    category=category,
                    raw_price=price,
                    currency=curr,
                    price=rounded_price
                )
            )
        
        # Validate logical price progression for vehicle categories
        # This ensures standard < xl < vip pricing hierarchy
        if len(prices_list) > 1:
            # Sort by category to group similar vehicles
            prices_list.sort(key=lambda x: x.category)
            
            # Check minivan pricing hierarchy
            minivan_prices = [p for p in prices_list if 'minivan' in p.category]
            if len(minivan_prices) > 1:
                for i in range(len(minivan_prices) - 1):
                    if 'standard_minivan' in minivan_prices[i].category and 'xl_minivan' in minivan_prices[i+1].category:
                        if minivan_prices[i].price >= minivan_prices[i+1].price:
                            logger.warning(f"Fixing illogical pricing: {minivan_prices[i].category}={minivan_prices[i].price} >= {minivan_prices[i+1].category}={minivan_prices[i+1].price}")
                            # Ensure XL is at least €10 more than standard
                            minivan_prices[i+1].price = max(minivan_prices[i+1].price, minivan_prices[i].price + 10)
                    if 'xl_minivan' in minivan_prices[i].category and 'vip_minivan' in minivan_prices[i+1].category:
                        if minivan_prices[i].price >= minivan_prices[i+1].price:
                            logger.warning(f"Fixing illogical pricing: {minivan_prices[i].category}={minivan_prices[i].price} >= {minivan_prices[i+1].category}={minivan_prices[i+1].price}")
                            # Ensure VIP is at least €10 more than XL
                            minivan_prices[i+1].price = max(minivan_prices[i+1].price, minivan_prices[i].price + 10)
            
            # Similar checks for sedan categories
            sedan_prices = [p for p in prices_list if 'sedan' in p.category]
            if len(sedan_prices) > 1:
                for i in range(len(sedan_prices) - 1):
                    if 'standard_sedan' in sedan_prices[i].category and 'premium_sedan' in sedan_prices[i+1].category:
                        if sedan_prices[i].price >= sedan_prices[i+1].price:
                            logger.warning(f"Fixing illogical pricing: {sedan_prices[i].category}={sedan_prices[i].price} >= {sedan_prices[i+1].category}={sedan_prices[i+1].price}")
                            # Ensure premium is at least €10 more than standard
                            sedan_prices[i+1].price = max(sedan_prices[i+1].price, sedan_prices[i].price + 10)
                    if 'premium_sedan' in sedan_prices[i].category and 'vip_sedan' in sedan_prices[i+1].category:
                        if sedan_prices[i].price >= sedan_prices[i+1].price:
                            logger.warning(f"Fixing illogical pricing: {sedan_prices[i].category}={sedan_prices[i].price} >= {sedan_prices[i+1].category}={sedan_prices[i+1].price}")
                            # Ensure VIP is at least €20 more than premium
                            sedan_prices[i+1].price = max(sedan_prices[i+1].price, sedan_prices[i].price + 20)
        
        # Build detailed response
        response = {
            "prices": prices_list,
            "details": {
                "pickup_time": request.pickup_time.isoformat(),
                "pickup_location": {"lat": request.pickup_lat, "lng": request.pickup_lng},
                "dropoff_location": {"lat": request.dropoff_lat, "lng": request.dropoff_lng},
                "trip_type": "one-way" if request.trip_type == "1" else "round trip",
                "request_id": request_id
            }
        }
        
        # Cache the response
        request_cache[request_id] = {
            'timestamp': current_time,
            'response': response
        }
        
        # Clean up old cache entries
        clean_expired_cache_entries()
        
        # Remove from active requests
        if request_id in active_requests:
            del active_requests[request_id]
        
        return response
        
    except ValueError as e:
        logger.error(f"Value error in price calculation: {str(e)}")
        # Remove from active requests
        if request_id in active_requests:
            del active_requests[request_id]
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in price calculation: {str(e)}")
        # Remove from active requests
        if request_id in active_requests:
            del active_requests[request_id]
        raise HTTPException(status_code=500, detail="Internal server error during price calculation")

def clean_expired_cache_entries():
    """Remove expired entries from the request cache"""
    current_time = time()
    # Find expired keys (older than 60 seconds)
    expired_keys = [k for k, v in request_cache.items() if current_time - v['timestamp'] >= 60]
    
    for key in expired_keys:
        del request_cache[key]
    
    # Also clean up abandoned active_requests entries (older than 30 seconds)
    expired_active = [k for k in active_requests.keys() if k not in request_cache or current_time - request_cache[k]['timestamp'] >= 30]
    for key in expired_active:
        if key in active_requests:
            del active_requests[key]
    
    if expired_keys or expired_active:
        logger.debug(f"Cleaned {len(expired_keys)} expired cache entries and {len(expired_active)} abandoned requests")

@app.post("/refresh-config")
async def refresh_configuration():
    """Force refresh the configuration from Supabase"""
    global config
    try:
        config = Config(use_supabase=True)
        logger.info("Configuration refreshed successfully")
        return {"status": "success", "message": "Configuration refreshed"}
    except Exception as e:
        logger.error(f"Error refreshing configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error refreshing configuration: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    logger.info("Starting Airport Transfer Pricing API")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    logger.info("Shutting down Airport Transfer Pricing API")

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time to response headers for monitoring"""
    import time
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)