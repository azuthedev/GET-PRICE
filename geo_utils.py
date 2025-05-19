import math
import json
import logging
import os
import requests
import polyline
from rtree import index
from shapely.geometry import LineString, Point, shape, mapping
from typing import Dict, Tuple, List, Any, Optional

logger = logging.getLogger(__name__)

def load_geo_data(geojson_path: str = "data/editedITprov.geojson") -> Dict[str, Any]:
    """
    Load GeoJSON data of Italian provinces and build an R-tree spatial index
    
    Args:
        geojson_path: Path to the GeoJSON file
        
    Returns:
        Dictionary containing loaded geo data including R-tree index
    """
    try:
        # Check if the GeoJSON file exists
        if not os.path.exists(geojson_path):
            logger.error(f"GeoJSON file not found at {geojson_path}")
            return create_emergency_geo_data()
        
        # Load the GeoJSON data
        with open(geojson_path, 'r') as f:
            geojson_data = json.load(f)
        
        # Build R-tree index
        idx = index.Index()
        provinces = {}
        province_codes = {}
        
        for i, feature in enumerate(geojson_data['features']):
            try:
                # Extract province data including province code (prov_acr)
                province_id = str(feature['properties'].get('prov_istat', f"PROV_{i}"))
                prov_acr = str(feature['properties'].get('prov_acr', f"DEFAULT"))
                
                # Store the province data
                provinces[province_id] = {
                    'name': feature['properties'].get('prov_name', f"Province {i}"),
                    'geometry': shape(feature['geometry']),
                    'properties': feature['properties'],
                    'code': prov_acr  # Store the province code for lookup
                }
                
                # Store province ID by code for reverse lookup
                province_codes[prov_acr] = province_id
                
                # Add to R-tree index
                bounds = provinces[province_id]['geometry'].bounds
                idx.insert(i, bounds, obj=province_id)
                
            except Exception as e:
                logger.error(f"Error processing feature {i}: {str(e)}")
                continue
        
        logger.info(f"Loaded {len(provinces)} provinces from GeoJSON")
        
        return {
            'provinces': provinces,
            'province_codes': province_codes,
            'rtree': idx,
            'geojson': geojson_data
        }
    except Exception as e:
        logger.error(f"Error loading GeoJSON data: {str(e)}")
        # Create and return minimal geo data for fallback
        return create_emergency_geo_data()

def create_emergency_geo_data() -> Dict[str, Any]:
    """Create minimal geo data as emergency fallback"""
    logger.warning("Creating emergency geo data")
    
    # Create a single 'DEFAULT' zone covering all of Italy
    default_italy = {
        'name': 'Italy',
        'geometry': shape({
            'type': 'Polygon',
            'coordinates': [[[6.0, 36.0], [19.0, 36.0], [19.0, 48.0], [6.0, 48.0], [6.0, 36.0]]]
        }),
        'properties': {'prov_acr': 'DEFAULT', 'prov_name': 'Italy'},
        'code': 'DEFAULT'
    }
    
    # Create a minimal R-tree
    idx = index.Index()
    idx.insert(0, default_italy['geometry'].bounds, obj='DEFAULT')
    
    # Create simplified GeoJSON
    geojson_data = {
        'type': 'FeatureCollection',
        'features': [{
            'type': 'Feature',
            'properties': {'prov_acr': 'DEFAULT', 'prov_name': 'Italy', 'prov_istat': 'DEFAULT'},
            'geometry': {
                'type': 'Polygon',
                'coordinates': [[[6.0, 36.0], [19.0, 36.0], [19.0, 48.0], [6.0, 48.0], [6.0, 36.0]]]
            }
        }]
    }
    
    return {
        'provinces': {'DEFAULT': default_italy},
        'province_codes': {'DEFAULT': 'DEFAULT'},
        'rtree': idx,
        'geojson': geojson_data
    }

def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """
    Calculate the great-circle distance between two coordinates
    using the haversine formula
    
    Args:
        coord1: (latitude, longitude) of first point
        coord2: (latitude, longitude) of second point
        
    Returns:
        Distance in kilometers
    """
    try:
        # Earth radius in kilometers
        R = 6371.0
        
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        distance = R * c
        
        return distance
    except Exception as e:
        logger.error(f"Error calculating haversine distance: {str(e)}")
        # Return a small positive value as fallback
        return 0.1

def calculate_distance(pickup: Tuple[float, float], dropoff: Tuple[float, float]) -> float:
    """
    Calculate distance between pickup and dropoff locations
    
    Args:
        pickup: (latitude, longitude) of pickup
        dropoff: (latitude, longitude) of dropoff
        
    Returns:
        Distance in kilometers
    """
    # For simplicity, using haversine distance
    # In production, consider using OSRM for more accurate driving distance
    return haversine_distance(pickup, dropoff)

def get_mapbox_route(
    pickup: Tuple[float, float],
    dropoff: Tuple[float, float],
    depart_at: str = None
) -> Dict[str, Any]:
    """
    Get route information from Mapbox API
    
    Args:
        pickup: (latitude, longitude) of pickup
        dropoff: (latitude, longitude) of dropoff
        depart_at: ISO format datetime string for departure time
    
    Returns:
        Dictionary with route information including distance, duration, and geometry
    """
    try:
        mapbox_api_key = os.getenv("MAPBOX_API_KEY")
        
        if not mapbox_api_key:
            logger.error("MAPBOX_API_KEY not found in environment variables")
            return None
        
        # Format coordinates with 5 decimal points
        pickup_lng = format(pickup[1], '.5f')
        pickup_lat = format(pickup[0], '.5f')
        dropoff_lng = format(dropoff[1], '.5f')
        dropoff_lat = format(dropoff[0], '.5f')
        
        # Build URL
        base_url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{pickup_lng},{pickup_lat};{dropoff_lng},{dropoff_lat}"
        
        params = {
            "alternatives": "false",
            "geometries": "polyline",
            "language": "en",
            "overview": "full",
            "steps": "true",
            "access_token": mapbox_api_key
        }
        
        # Add departure time if provided
        if depart_at:
            params["depart_at"] = depart_at
        
        response = requests.get(base_url, params=params)
        
        if response.status_code != 200:
            logger.error(f"Mapbox API error: {response.status_code} - {response.text}")
            return None
        
        data = response.json()
        
        if not data.get("routes") or len(data["routes"]) == 0:
            logger.error("No routes found in Mapbox response")
            return None
        
        route = data["routes"][0]
        
        return {
            "distance": route["distance"] / 1000,  # Convert meters to kilometers
            "duration": route["duration"] / 60,    # Convert seconds to minutes
            "geometry": route["geometry"]
        }
        
    except Exception as e:
        logger.error(f"Error getting Mapbox route: {str(e)}")
        return None

def decode_polyline_to_coordinates(encoded_polyline: str) -> List[Tuple[float, float]]:
    """
    Decode a polyline string to a list of coordinates
    
    Args:
        encoded_polyline: Encoded polyline string from Mapbox
    
    Returns:
        List of (latitude, longitude) tuples
    """
    try:
        # Decode polyline
        coords = polyline.decode(encoded_polyline)
        
        # Mapbox returns coordinates as (lat, lng)
        return coords
        
    except Exception as e:
        logger.error(f"Error decoding polyline: {str(e)}")
        return []

def interpolate_points(start: Tuple[float, float], end: Tuple[float, float], num_points: int = 10) -> List[Tuple[float, float]]:
    """
    Generate interpolated points along a straight line between start and end coordinates
    
    Args:
        start: (latitude, longitude) of start point
        end: (latitude, longitude) of end point
        num_points: Number of points to generate
        
    Returns:
        List of (latitude, longitude) tuples
    """
    points = []
    for i in range(num_points + 1):
        t = i / num_points
        lat = start[0] + t * (end[0] - start[0])
        lng = start[1] + t * (end[1] - start[1])
        points.append((lat, lng))
    return points

def calculate_route_segments(
    pickup: Tuple[float, float], 
    dropoff: Tuple[float, float], 
    num_segments: int = 10,
    use_mapbox: bool = True,
    depart_at: str = None
) -> List[Tuple[float, float]]:
    """
    Calculate route segments between pickup and dropoff
    
    Args:
        pickup: (latitude, longitude) of pickup
        dropoff: (latitude, longitude) of dropoff
        num_segments: Number of segments to create
        use_mapbox: Whether to use Mapbox API for routing
        depart_at: ISO format datetime string for departure time
        
    Returns:
        List of (latitude, longitude) points along the route
    """
    # Check for identical coordinates
    if pickup[0] == dropoff[0] and pickup[1] == dropoff[1]:
        return [pickup]
    
    # Check for very short distance
    if haversine_distance(pickup, dropoff) < 0.1:  # Less than 100 meters
        return [pickup, dropoff]
    
    # Try using Mapbox API if requested
    if use_mapbox:
        try:
            mapbox_route = get_mapbox_route(pickup, dropoff, depart_at)
            
            if mapbox_route and mapbox_route.get("geometry"):
                route_points = decode_polyline_to_coordinates(mapbox_route["geometry"])
                
                if route_points and len(route_points) > 1:
                    logger.info(f"Using Mapbox route with {len(route_points)} points")
                    return route_points
                else:
                    logger.warning("Mapbox returned empty or invalid route, falling back to linear interpolation")
            else:
                logger.warning("No valid geometry found in Mapbox response, falling back to linear interpolation")
        except Exception as e:
            logger.error(f"Error using Mapbox routing: {str(e)}, falling back to linear interpolation")
    
    # Fallback to linear interpolation
    logger.info("Using linear interpolation for route")
    return interpolate_points(pickup, dropoff, num_segments)

def determine_zones_crossed(route_points: List[Tuple[float, float]], geo_data: Dict[str, Any]) -> Dict[str, float]:
    """
    Determine which zones the route passes through and the distance in each
    
    Args:
        route_points: List of (latitude, longitude) tuples along the route
        geo_data: Loaded geographic data including R-tree index
        
    Returns:
        Dictionary mapping zone codes (prov_acr) to distance in kilometers
    """
    try:
        rtree_idx = geo_data['rtree']
        provinces = geo_data['provinces']
        
        # Handle edge case of extremely short routes or identical points
        if len(route_points) <= 1:
            point = Point(route_points[0][1], route_points[0][0])
            potential_zones = list(rtree_idx.intersection((point.x, point.y, point.x, point.y), objects=True))
            
            for zone in potential_zones:
                province_id = zone.object
                if provinces[province_id]['geometry'].contains(point):
                    # Use the province code (prov_acr) as the key
                    prov_code = provinces[province_id].get('code', 'DEFAULT')
                    return {prov_code: 0.1}  # Minimal distance
            
            return {'DEFAULT': 0.1}  # Fallback
        
        # For routes with only 2 points that are very close
        if len(route_points) == 2 and haversine_distance(route_points[0], route_points[1]) < 0.1:
            point = Point(route_points[0][1], route_points[0][0])
            potential_zones = list(rtree_idx.intersection((point.x, point.y, point.x, point.y), objects=True))
            
            for zone in potential_zones:
                province_id = zone.object
                if provinces[province_id]['geometry'].contains(point):
                    # Use the province code (prov_acr) as the key
                    prov_code = provinces[province_id].get('code', 'DEFAULT')
                    return {prov_code: haversine_distance(route_points[0], route_points[1])}
            
            return {'DEFAULT': haversine_distance(route_points[0], route_points[1])}
        
        # Process normal routes with multiple segments
        zone_distances = {}
        
        # Create line segments between consecutive points
        for i in range(len(route_points) - 1):
            start = route_points[i]
            end = route_points[i + 1]
            
            segment_distance = haversine_distance(start, end)
            
            # Skip extremely short segments
            if segment_distance < 0.001:  # Less than 1 meter
                continue
            
            # Create a LineString geometry for this segment
            segment = LineString([(start[1], start[0]), (end[1], end[0])])
            
            # Find potential zones that intersect with the segment's bounding box
            segment_bounds = segment.bounds
            potential_zones = list(rtree_idx.intersection(segment_bounds, objects=True))
            
            zones_for_segment = set()
            
            for zone in potential_zones:
                province_id = zone.object
                province_geom = provinces[province_id]['geometry']
                
                if segment.intersects(province_geom):
                    # Use province code (prov_acr) instead of ID
                    prov_code = provinces[province_id].get('code', 'DEFAULT')
                    zones_for_segment.add(prov_code)
            
            # If the segment doesn't intersect any zone, assign it to a default zone
            if not zones_for_segment:
                zones_for_segment = {'DEFAULT'}
            
            # Distribute the segment distance among the zones it passes through
            for zone in zones_for_segment:
                zone_distances[zone] = zone_distances.get(zone, 0) + segment_distance / len(zones_for_segment)
        
        return zone_distances
    
    except Exception as e:
        logger.error(f"Error determining zones crossed: {str(e)}")
        # Return a default in case of error
        return {'DEFAULT': calculate_distance(route_points[0], route_points[-1])}

def check_fixed_price(
    pickup: Tuple[float, float], 
    dropoff: Tuple[float, float], 
    vehicle_category: str,
    fixed_prices: List[Dict[str, Any]]
) -> Optional[float]:
    """
    Check if there's a fixed price override for the given route
    
    Args:
        pickup: (latitude, longitude) of pickup
        dropoff: (latitude, longitude) of dropoff
        vehicle_category: Type of vehicle
        fixed_prices: List of fixed price configurations
        
    Returns:
        Fixed price if found, None otherwise
    """
    try:
        # Handle identical coordinates
        if pickup[0] == dropoff[0] and pickup[1] == dropoff[1]:
            logger.warning("Identical pickup and dropoff coordinates provided for fixed price check")
            return None
        
        pickup_point = Point(pickup[1], pickup[0])
        dropoff_point = Point(dropoff[1], dropoff[0])
        
        for fixed_price in fixed_prices:
            if fixed_price.get('vehicle_category', '').lower() != vehicle_category.lower():
                continue
            
            try:
                pickup_area = fixed_price.get('pickup_area')
                dropoff_area = fixed_price.get('dropoff_area')
                
                if not pickup_area or not dropoff_area:
                    continue
                
                pickup_polygon = shape(pickup_area)
                dropoff_polygon = shape(dropoff_area)
                
                # Check if pickup and dropoff match the fixed price areas
                pickup_match = pickup_polygon.contains(pickup_point)
                dropoff_match = dropoff_polygon.contains(dropoff_point)
                
                if pickup_match and dropoff_match:
                    return fixed_price.get('price', None)
                
                # Check the reverse direction if bidirectional is True
                if fixed_price.get('bidirectional', False):
                    reverse_pickup_match = dropoff_polygon.contains(pickup_point)
                    reverse_dropoff_match = pickup_polygon.contains(dropoff_point)
                    
                    if reverse_pickup_match and reverse_dropoff_match:
                        return fixed_price.get('price', None)
            except Exception as e:
                logger.error(f"Error checking fixed price for entry {fixed_price.get('name', 'unknown')}: {str(e)}")
                continue
        
        return None
    except Exception as e:
        logger.error(f"Error in fixed price check: {str(e)}")
        return None
