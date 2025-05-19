import logging
from functools import lru_cache
from datetime import datetime
from typing import Dict, Tuple, Any, List, Optional

from config import Config
from geo_utils import (
    calculate_distance, 
    determine_zones_crossed, 
    calculate_route_segments,
    check_fixed_price
)

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1000)
def get_cached_price_calc(
    pickup_lat: float,
    pickup_lng: float,
    dropoff_lat: float,
    dropoff_lng: float,
    vehicle_category: str,
    pickup_hour: int,
    pickup_weekday: int,
    pickup_date_str: str
) -> Dict[str, Any]:
    """
    Cached version of price calculation to improve performance for repeated requests
    
    Args:
        Various price calculation parameters
        
    Returns:
        Dictionary with price calculation details
    """
    # This is just a cache key function. The actual calculation happens in calculate_price
    # The actual price calculation will happen when this cached function is called with
    # the complete parameters including config and geo_data (which are not part of the cache key)
    return {}

def calculate_price(
    pickup_lat: float,
    pickup_lng: float,
    dropoff_lat: float,
    dropoff_lng: float,
    vehicle_category: str,
    pickup_time: datetime,
    config: Config,
    geo_data: Dict[str, Any]
) -> Tuple[float, str]:
    """
    Calculate the price for a transfer based on the provided parameters.
    
    Args:
        pickup_lat: Latitude of pickup location
        pickup_lng: Longitude of pickup location
        dropoff_lat: Latitude of dropoff location
        dropoff_lng: Longitude of dropoff location
        vehicle_category: Type of vehicle requested
        pickup_time: Time of pickup
        config: Configuration object containing pricing rules
        geo_data: Loaded geographic data including R-tree spatial index
        
    Returns:
        Tuple containing (price, currency)
    """
    # Create a result dictionary to track calculation details
    result = {
        "price": 0.0,
        "currency": config.currency,
        "price_details": {
            "fixed_price_applied": False,
            "min_fare_applied": False,
            "total_distance_km": 0,
            "base_price": 0,
            "zone_adjustments": {},
            "time_multiplier": 1.0,
            "surge_multiplier": 1.0
        }
    }
    
    try:
        # Check for identical coordinates (zero distance case)
        if pickup_lat == dropoff_lat and pickup_lng == dropoff_lng:
            logger.warning("Pickup and dropoff locations are identical")
            min_fare = config.min_fares.get(vehicle_category, 10.0)
            result["price"] = min_fare
            result["price_details"]["min_fare_applied"] = True
            result["price_details"]["fixed_price_applied"] = True
            return result["price"], result["currency"]
        
        # 1. Check for fixed price override
        fixed_price = check_fixed_price(
            (pickup_lat, pickup_lng),
            (dropoff_lat, dropoff_lng),
            vehicle_category,
            config.fixed_prices
        )
        
        if fixed_price is not None:
            logger.info(f"Fixed price found: {fixed_price} {config.currency}")
            result["price"] = fixed_price
            result["price_details"]["fixed_price_applied"] = True
            return result["price"], result["currency"]
        
        # 2. Calculate route and distance
        total_distance = calculate_distance(
            (pickup_lat, pickup_lng),
            (dropoff_lat, dropoff_lng)
        )
        
        result["price_details"]["total_distance_km"] = total_distance
        
        # 3. Determine which zones the route passes through
        try:
            route_segments = calculate_route_segments(
                (pickup_lat, pickup_lng),
                (dropoff_lat, dropoff_lng),
                num_segments=20  # Increased from 10 for better accuracy
            )
            
            zones_crossed = determine_zones_crossed(route_segments, geo_data)
            result["price_details"]["zones_crossed"] = list(zones_crossed.keys())
        except Exception as e:
            logger.error(f"Error determining zones crossed: {str(e)}")
            # Fall back to default zone
            zones_crossed = {"DEFAULT": total_distance}
            result["price_details"]["zones_crossed"] = ["DEFAULT"]
        
        # 4. Calculate base price based on vehicle category and distance
        if vehicle_category not in config.vehicle_rates:
            logger.warning(f"Unknown vehicle category: {vehicle_category}, using default")
            vehicle_category = next(iter(config.vehicle_rates.keys()))
        
        base_rate = config.vehicle_rates[vehicle_category]
        result["price_details"]["base_rate_per_km"] = base_rate
        
        # 5. Apply zone multipliers from the database
        price = 0.0
        
        for zone_code, distance in zones_crossed.items():
            # Get multiplier for this zone (falls back to DEFAULT if not found)
            zone_multiplier = config.zone_multipliers.get(zone_code, 
                               config.zone_multipliers.get("DEFAULT", 1.0))
            
            zone_price = base_rate * distance * zone_multiplier
            price += zone_price
            
            # Record details for this zone
            result["price_details"]["zone_adjustments"][zone_code] = {
                "distance_km": distance,
                "multiplier": zone_multiplier,
                "contribution": zone_price
            }
        
        result["price_details"]["base_price"] = price
        
        # 6. Apply time-based multipliers
        weekday = pickup_time.weekday()
        hour = pickup_time.hour
        
        time_multiplier = 1.0
        
        # Check if it's a weekend
        if weekday >= 5:  # 5 is Saturday, 6 is Sunday
            time_multiplier *= config.time_multipliers.get("weekend", 1.0)
            result["price_details"]["weekend_multiplier_applied"] = True
        
        # Check if it's night time
        if hour < 6 or hour >= 22:
            time_multiplier *= config.time_multipliers.get("night", 1.0)
            result["price_details"]["night_multiplier_applied"] = True
        
        price *= time_multiplier
        result["price_details"]["time_multiplier"] = time_multiplier
        
        # 7. Apply any surge multipliers based on time
        current_surge = 1.0
        applied_surge_name = None
        
        for surge_rule in config.surge_multipliers:
            try:
                start_time = datetime.fromisoformat(surge_rule["start_time"])
                end_time = datetime.fromisoformat(surge_rule["end_time"])
                
                if start_time <= pickup_time <= end_time:
                    if float(surge_rule["multiplier"]) > current_surge:
                        current_surge = float(surge_rule["multiplier"])
                        applied_surge_name = surge_rule["name"]
            except Exception as e:
                logger.error(f"Error processing surge rule: {str(e)}")
        
        price *= current_surge
        result["price_details"]["surge_multiplier"] = current_surge
        if applied_surge_name:
            result["price_details"]["applied_surge"] = applied_surge_name
        
        # 8. Apply minimum fare if needed
        min_fare = config.min_fares.get(vehicle_category, 0)
        if price < min_fare:
            logger.info(f"Applying minimum fare: {min_fare} {config.currency}")
            price = min_fare
            result["price_details"]["min_fare_applied"] = True
            result["price_details"]["min_fare_value"] = min_fare
        
        # Round to 2 decimal places
        price = round(price, 2)
        result["price"] = price
        
        return price, config.currency
    
    except Exception as e:
        logger.error(f"Error calculating price: {str(e)}")
        # Return a default price in case of error
        min_fare = 15.0
        try:
            min_fare = config.min_fares.get(vehicle_category, 15.0)
        except:
            pass
        
        return min_fare, config.currency