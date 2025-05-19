import logging
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from functools import lru_cache
import math

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
    price: float
    currency: str
    final_price: float

class PriceResponse(BaseModel):
    prices: List[VehiclePriceInfo]
    details: Optional[Dict[str, Any]] = None

def round_to_nearest_10(price: float) -> float:
    """Round the price to the nearest 10 euros for a premium look"""
    return round(price / 10.0) * 10.0

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
    logger.info(f"Received price check request from "
                f"({request.pickup_lat}, {request.pickup_lng}) to ({request.dropoff_lat}, {request.dropoff_lng}) "
                f"with trip_type={request.trip_type}")
    
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
            
            # Round to the nearest 10 euros
            final_price = round_to_nearest_10(price)
            
            prices_list.append(
                VehiclePriceInfo(
                    category=category,
                    price=price,
                    currency=curr,
                    final_price=final_price
                )
            )
        
        # Build detailed response
        response = {
            "prices": prices_list,
            "details": {
                "pickup_time": request.pickup_time.isoformat(),
                "pickup_location": {"lat": request.pickup_lat, "lng": request.pickup_lng},
                "dropoff_location": {"lat": request.dropoff_lat, "lng": request.dropoff_lng},
                "trip_type": "one-way" if request.trip_type == "1" else "round trip"
            }
        }
        
        return response
        
    except ValueError as e:
        logger.error(f"Value error in price calculation: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in price calculation: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during price calculation")

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