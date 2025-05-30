import os
import logging
from typing import Dict, Optional, Any, List
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class SupabaseManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SupabaseManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize Supabase client with environment variables"""
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        self.client = None
        
        if not self.supabase_url or not self.supabase_key:
            logger.warning("Supabase credentials not found in environment variables. "
                         "Using fallback configuration instead.")
        else:
            try:
                self.client = create_client(self.supabase_url, self.supabase_key)
                logger.info("Supabase client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
    
    def get_zone_multipliers(self) -> Dict[str, float]:
        """
        Fetch zone multipliers from Supabase
        
        Returns:
            Dictionary mapping zone codes (prov_acr) to multiplier values
        """
        if not self.client:
            logger.warning("Supabase client not initialized. Returning empty zone multipliers.")
            return {}
        
        try:
            # Join zones and zone_multipliers to get the province codes (prov_acr) 
            # with their corresponding multipliers
            response = self.client.rpc(
                'get_zone_multipliers_with_codes',
                {}
            ).execute()
            
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error fetching zone multipliers: {response.error}")
                
                # Fallback: try to get zone_multipliers directly if RPC fails
                fallback_response = self.client.table('zone_multipliers').select('*').execute()
                if hasattr(fallback_response, 'error') and fallback_response.error is not None:
                    logger.error(f"Fallback also failed: {fallback_response.error}")
                    return {}
                
                # If we got data but it doesn't have the expected format,
                # use a default mapping of zone_id -> multiplier
                zone_multipliers = {}
                for item in fallback_response.data:
                    # Use zone_id as the key if we don't have province codes
                    zone_multipliers[str(item['zone_id'])] = float(item['multiplier'])
                
                logger.info(f"Loaded {len(zone_multipliers)} zone multipliers from Supabase (fallback mode)")
                return zone_multipliers
            
            # Convert the response to a dictionary with province code as the key
            zone_multipliers = {}
            for item in response.data:
                if 'prov_acr' in item and item['prov_acr']:
                    # Use province code (prov_acr) as the key
                    zone_multipliers[item['prov_acr']] = float(item['multiplier'])
                else:
                    # Fallback to zone_id if prov_acr is not available
                    zone_multipliers[str(item['zone_id'])] = float(item['multiplier'])
            
            # Always ensure DEFAULT is present
            if 'DEFAULT' not in zone_multipliers:
                zone_multipliers['DEFAULT'] = 1.0
                
            logger.info(f"Loaded {len(zone_multipliers)} zone multipliers from Supabase")
            return zone_multipliers
            
        except Exception as e:
            logger.error(f"Error fetching zone multipliers from Supabase: {e}")
            return {}
    
    def get_vehicle_base_prices(self) -> Dict[str, float]:
        """
        Fetch vehicle base prices from Supabase
        
        Returns:
            Dictionary mapping vehicle types to base prices
        """
        if not self.client:
            logger.warning("Supabase client not initialized. Returning empty vehicle base prices.")
            return {}
        
        try:
            response = self.client.table('vehicle_base_prices').select('vehicle_type, base_price_per_km').execute()
            
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error fetching vehicle base prices: {response.error}")
                return {}
            
            # Convert the response to a dictionary
            vehicle_prices = {}
            for item in response.data:
                vehicle_prices[item['vehicle_type']] = float(item['base_price_per_km'])
            
            logger.info(f"Loaded {len(vehicle_prices)} vehicle base prices from Supabase")
            return vehicle_prices
            
        except Exception as e:
            logger.error(f"Error fetching vehicle base prices from Supabase: {e}")
            return {}
    
    def get_fixed_routes(self) -> List[Dict[str, Any]]:
        """
        Fetch fixed route prices from Supabase and transform to the format
        expected by the pricing engine
        
        Returns:
            List of fixed route configurations
        """
        if not self.client:
            logger.warning("Supabase client not initialized. Returning empty fixed routes.")
            return []
        
        try:
            response = self.client.table('fixed_routes').select('*').execute()
            
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error fetching fixed routes: {response.error}")
                return []
            
            # Transform the data to match the expected format
            transformed_routes = []
            for route in response.data:
                try:
                    # Create a properly formatted fixed route entry
                    fixed_route = {
                        "name": route.get('origin_name', '') + ' to ' + route.get('destination_name', ''),
                        "vehicle_category": route.get('vehicle_type', ''),
                        "price": float(route.get('fixed_price', 0)),
                        "bidirectional": True  # Default to bidirectional
                    }
                    
                    # Add pickup_area and dropoff_area if they exist
                    if 'pickup_area' in route and route['pickup_area']:
                        fixed_route['pickup_area'] = route['pickup_area']
                    elif 'origin_polygon' in route and route['origin_polygon']:
                        fixed_route['pickup_area'] = route['origin_polygon']
                    
                    if 'dropoff_area' in route and route['dropoff_area']:
                        fixed_route['dropoff_area'] = route['dropoff_area']
                    elif 'destination_polygon' in route and route['destination_polygon']:
                        fixed_route['dropoff_area'] = route['destination_polygon']
                    
                    # Only add routes that have both pickup and dropoff areas
                    if 'pickup_area' in fixed_route and 'dropoff_area' in fixed_route:
                        transformed_routes.append(fixed_route)
                    else:
                        logger.warning(f"Fixed route {fixed_route['name']} missing required area polygons, skipping")
                
                except Exception as e:
                    logger.error(f"Error processing fixed route: {e}")
                    continue
            
            logger.info(f"Loaded {len(transformed_routes)} fixed routes from Supabase")
            return transformed_routes
            
        except Exception as e:
            logger.error(f"Error fetching fixed routes from Supabase: {e}")
            return []

    def create_supabase_functions(self):
        """
        Create necessary SQL functions in the Supabase database
        """
        if not self.client:
            logger.warning("Supabase client not initialized. Cannot create functions.")
            return False
        
        try:
            # Create function to get zone multipliers with province codes
            create_function_sql = """
            CREATE OR REPLACE FUNCTION get_zone_multipliers_with_codes()
            RETURNS TABLE (
                zone_id UUID,
                multiplier NUMERIC,
                prov_acr TEXT
            ) 
            LANGUAGE SQL
            AS $$
                SELECT 
                    zm.zone_id,
                    zm.multiplier,
                    z.prov_acr
                FROM 
                    zone_multipliers zm
                LEFT JOIN 
                    zones z ON zm.zone_id = z.id;
            $$;
            """
            
            # Execute the function creation
            response = self.client.rpc('exec_sql', {'sql': create_function_sql}).execute()
            
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error creating function: {response.error}")
                return False
            
            logger.info("Successfully created get_zone_multipliers_with_codes function")
            return True
            
        except Exception as e:
            logger.error(f"Error creating Supabase functions: {e}")
            return False