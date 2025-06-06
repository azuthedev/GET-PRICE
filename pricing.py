import logging
from functools import lru_cache
from datetime import datetime
from typing import Dict, Tuple, Any, List, Optional

from config import Config
from geo_utils import (
    calculate_distance, 
    determine_zones_crossed, 
    calculate_route_segments,
    check_fixed_price,
    get_route_with_fallbacks
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
    pickup_date_str: str,
    trip_type: str
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
    geo_data: Dict[str, Any],
    trip_type: str = "1"
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
        trip_type: "1" for one-way, "2" for round trip
        
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
            "trip_type": "one-way" if trip_type == "1" else "round trip"
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
        
        # Format pickup_time for routing APIs
        depart_at = pickup_time.strftime("%Y-%m-%dT%H:%M")
        
        # 1. Get route information from Google Maps (with fallbacks to Mapbox and Haversine)
        route_info = get_route_with_fallbacks(
            (pickup_lat, pickup_lng),
            (dropoff_lat, dropoff_lng),
            depart_at=depart_at
        )
        
        # Initialize total distance
        total_distance = 0
        route_points = []
        
        # If we got valid route info, use it
        if route_info:
            total_distance = route_info['distance']  # Already in kilometers
            result["price_details"]["route_source"] = route_info.get('source', 'unknown')
            result["price_details"]["estimated_duration_min"] = route_info.get('duration', 0)
            
            # Get route points for zone calculations
            if route_info.get('geometry'):
                route_points = calculate_route_segments(
                    (pickup_lat, pickup_lng),
                    (dropoff_lat, dropoff_lng),
                    use_routing_apis=True,
                    depart_at=depart_at
                )
                result["price_details"]["route_points_count"] = len(route_points)
            else:
                # Fallback to direct distance calculation and interpolation
                logger.warning("No route geometry available, using linear interpolation")
                total_distance = calculate_distance(
                    (pickup_lat, pickup_lng),
                    (dropoff_lat, dropoff_lng)
                )
                result["price_details"]["direct_distance_used"] = True
                
                # Get route points through interpolation
                route_points = calculate_route_segments(
                    (pickup_lat, pickup_lng),
                    (dropoff_lat, dropoff_lng),
                    num_segments=20,
                    use_routing_apis=False
                )
        else:
            # Complete fallback if no route info at all
            logger.error("No route information available, using direct distance")
            total_distance = calculate_distance(
                (pickup_lat, pickup_lng),
                (dropoff_lat, dropoff_lng)
            )
            result["price_details"]["direct_distance_used"] = True
            
            # Get route points through interpolation
            route_points = calculate_route_segments(
                (pickup_lat, pickup_lng),
                (dropoff_lat, dropoff_lng),
                num_segments=20,
                use_routing_apis=False
            )
        
        # Store one-way distance for reference
        one_way_distance = total_distance
        result["price_details"]["one_way_distance_km"] = one_way_distance
        
        # 2. Determine which zones the route passes through (before applying round trip)
        try:
            # Use the route points we already obtained
            zones_crossed = determine_zones_crossed(route_points, geo_data)
            result["price_details"]["zones_crossed"] = list(zones_crossed.keys())
        except Exception as e:
            logger.error(f"Error determining zones crossed: {str(e)}")
            # Fall back to default zone
            zones_crossed = {"DEFAULT": one_way_distance}
            result["price_details"]["zones_crossed"] = ["DEFAULT"]
            
        # Apply round trip multiplier if needed - AFTER zone calculation
        if trip_type == "2":
            total_distance *= 2
            result["price_details"]["round_trip_applied"] = True
            
        result["price_details"]["total_distance_km"] = total_distance
        
        # 3. Check for fixed price override
        fixed_price = check_fixed_price(
            (pickup_lat, pickup_lng),
            (dropoff_lat, dropoff_lng),
            vehicle_category,
            config.fixed_prices
        )
        
        if fixed_price is not None:
            logger.info(f"Fixed price found: {fixed_price} {config.currency}")
            price = fixed_price
            
            # Apply round trip doubling for fixed prices too
            if trip_type == "2":
                price *= 2
                logger.info(f"Applied round trip doubling to fixed price: {price} {config.currency}")
                
            result["price_details"]["fixed_price_applied"] = True
            
            # Get distance-based minimum fare
            distance_min_fare = get_distance_based_min_fare(one_way_distance, vehicle_category, config, trip_type)
            
            # Compare with distance-based minimum fare
            if price < distance_min_fare:
                price = distance_min_fare
                result["price_details"]["min_fare_applied"] = True
                result["price_details"]["min_fare_value"] = distance_min_fare
                logger.info(f"Distance-based minimum fare applied: {distance_min_fare} {config.currency}")
            
            result["price"] = price
            return price, result["currency"]
        
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
            
            # Apply round trip doubling to each zone price if needed
            if trip_type == "2":
                zone_price *= 2
                
            price += zone_price
            
            # Record details for this zone
            result["price_details"]["zone_adjustments"][zone_code] = {
                "distance_km": distance,
                "multiplier": zone_multiplier,
                "contribution": zone_price,
                "doubled_for_round_trip": trip_type == "2"
            }
        
        result["price_details"]["base_price"] = price
        
        # Time-based multipliers removed as requested
        
        # 6. Apply distance-based minimum fare if needed
        distance_min_fare = get_distance_based_min_fare(one_way_distance, vehicle_category, config, trip_type)
        
        if price < distance_min_fare:
            logger.info(f"Applying distance-based minimum fare: {distance_min_fare} {config.currency}")
            price = distance_min_fare
            result["price_details"]["min_fare_applied"] = True
            result["price_details"]["min_fare_value"] = distance_min_fare
        
        # Round to 2 decimal places
        price = round(price, 2)
        result["price"] = price
        
        return price, result["currency"]
    
    except Exception as e:
        logger.error(f"Error calculating price: {str(e)}")
        # Return a default price in case of error
        min_fare = 15.0
        try:
            min_fare = config.min_fares.get(vehicle_category, 15.0)
            # Double the minimum fare for round trips
            if trip_type == "2":
                min_fare *= 2
        except:
            pass
        
        return min_fare, result["currency"]

def get_distance_based_min_fare(
    distance: float,
    vehicle_category: str,
    config: Config,
    trip_type: str = "1"
) -> float:
    """
    Determine the appropriate minimum fare based on distance tier
    
    Args:
        distance: One-way distance in kilometers
        vehicle_category: Type of vehicle
        config: Configuration object
        trip_type: "1" for one-way, "2" for round trip
        
    Returns:
        Minimum fare applicable for the distance and vehicle
    """
    # Default minimum fare as fallback
    default_min_fare = config.min_fares.get(vehicle_category, 10.0)
    
    # Determine the appropriate distance tier
    if distance <= 5:
        tier = "0-5"
    elif distance <= 20:
        tier = "5-20"
    elif distance <= 50:
        tier = "20-50"
    else:
        # For distances > 50km, use the regular minimum fare
        tier = None
    
    # Get the distance-based minimum fare if available
    if tier and tier in config.distance_based_min_fares:
        min_fare = config.distance_based_min_fares[tier].get(vehicle_category, default_min_fare)
    else:
        min_fare = default_min_fare
    
    # Double for round trips
    if trip_type == "2":
        min_fare *= 2
    
    return min_fare