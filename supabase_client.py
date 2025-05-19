import os
import logging
from typing import Dict, Optional, Any
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
            Dictionary mapping zone IDs to multiplier values
        """
        if not self.client:
            logger.warning("Supabase client not initialized. Returning empty zone multipliers.")
            return {}
        
        try:
            response = self.client.table('zone_multipliers').select('zone_id, multiplier').execute()
            
            if hasattr(response, 'error') and response.error is not None:
                logger.error(f"Error fetching zone multipliers: {response.error}")
                return {}
            
            # Convert the response to a dictionary
            zone_multipliers = {}
            for item in response.data:
                zone_multipliers[item['zone_id']] = float(item['multiplier'])
            
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
    
    def get_fixed_routes(self) -> list:
        """
        Fetch fixed route prices from Supabase
        
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
            
            logger.info(f"Loaded {len(response.data)} fixed routes from Supabase")
            return response.data
            
        except Exception as e:
            logger.error(f"Error fetching fixed routes from Supabase: {e}")
            return []