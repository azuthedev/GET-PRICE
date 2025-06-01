import json
import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import the Supabase manager
from supabase_client import SupabaseManager

logger = logging.getLogger(__name__)

class Config:
    def __init__(self, config_dir: str = "config", use_supabase: bool = True):
        """
        Load configuration from JSON files and/or Supabase
        
        Args:
            config_dir: Directory containing config files
            use_supabase: Whether to try loading config from Supabase
        """
        self.config_dir = config_dir
        self.use_supabase = use_supabase
        
        # Ensure config directory exists
        os.makedirs(config_dir, exist_ok=True)
        
        # Currency for all prices
        self.currency = os.getenv("DEFAULT_CURRENCY", "EUR")
        
        # Initialize Supabase client if needed
        self.supabase = SupabaseManager() if use_supabase else None
        
        # Load all configurations
        self._load_all_configs()
        
        # Validate configurations
        self.validate_config()
    
    def _load_all_configs(self):
        """Load all configurations from Supabase and fallback to JSON files"""
        # First, try to load from Supabase if enabled
        supabase_vehicle_rates = {}
        supabase_zone_multipliers = {}
        supabase_fixed_prices = []
        
        if self.use_supabase and self.supabase and self.supabase.client:
            try:
                supabase_vehicle_rates = self.supabase.get_vehicle_base_prices()
                supabase_zone_multipliers = self.supabase.get_zone_multipliers()
                supabase_fixed_prices = self.supabase.get_fixed_routes()
                logger.info("Successfully loaded configurations from Supabase")
            except Exception as e:
                logger.error(f"Error loading from Supabase: {e}. Falling back to JSON configs.")
        
        # Load configs with fallback to JSON files
        self.vehicle_rates = supabase_vehicle_rates if supabase_vehicle_rates else self._load_or_create_config('vehicle_rates.json', self._default_vehicle_rates())
        self.zone_multipliers = supabase_zone_multipliers if supabase_zone_multipliers else self._load_or_create_config('zone_multipliers.json', self._default_zone_multipliers())
        self.time_multipliers = self._load_or_create_config('time_multipliers.json', self._default_time_multipliers())
        self.fixed_prices = supabase_fixed_prices if supabase_fixed_prices else self._load_or_create_config('fixed_prices.json', self._default_fixed_prices())
        self.min_fares = self._load_or_create_config('min_fares.json', self._default_min_fares())
        self.distance_based_min_fares = self._load_or_create_config('distance_based_min_fares.json', self._default_distance_based_min_fares())
    
    def _load_or_create_config(self, filename: str, default_config: Any) -> Any:
        """
        Load a config file or create it with default values if it doesn't exist
        
        Args:
            filename: Name of the config file
            default_config: Default configuration to use if file doesn't exist
            
        Returns:
            Loaded configuration
        """
        file_path = os.path.join(self.config_dir, filename)
        
        if not os.path.exists(file_path):
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            logger.info(f"Created default configuration file: {filename}")
        
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config file {filename}: {e}. Using default configuration.")
            return default_config
    
    def _default_vehicle_rates(self) -> Dict[str, float]:
        """Default base rates per km for each vehicle category"""
        return {
            # Sedans
            "standard_sedan": 2.6,
            "premium_sedan": 3.0,
            "vip_sedan": 4.0,
            
            # Minivans
            "standard_minivan": 3.0,
            "xl_minivan": 3.4,
            "vip_minivan": 3.6,
            
            # Sprinters
            "sprinter_8_pax": 4.6,
            "sprinter_16_pax": 7.4,
            "sprinter_21_pax": 11.2,
            
            # Coach
            "coach_51_pax": 20.0
        }
    
    def _default_zone_multipliers(self) -> Dict[str, float]:
        """Default multipliers for each zone/province"""
        return {
            "RM": 1.0,  # Rome
            "MI": 1.0,  # Milan
            "FI": 1.0,  # Florence
            "DEFAULT": 1.0  # Default for zones not specifically configured
        }
    
    def _default_time_multipliers(self) -> Dict[str, float]:
        """Default multipliers for different time periods"""
        return {
            "night": 1.0,  # Setting to 1.0 instead of 1.25 (no multiplier effect)
            "weekend": 1.0  # Setting to 1.0 instead of 1.15 (no multiplier effect)
        }
    
    def _default_fixed_prices(self) -> List[Dict[str, Any]]:
        """Default fixed price overrides"""
        return [
            {
                "name": "Rome Airport to City Center",
                "vehicle_category": "standard_sedan",
                "pickup_area": {
                    "type": "Polygon",
                    "coordinates": [[[12.2, 41.7], [12.3, 41.7], [12.3, 41.8], [12.2, 41.8], [12.2, 41.7]]]
                },
                "dropoff_area": {
                    "type": "Polygon",
                    "coordinates": [[[12.4, 41.9], [12.5, 41.9], [12.5, 42.0], [12.4, 42.0], [12.4, 41.9]]]
                },
                "price": 50.0,
                "bidirectional": True
            },
            {
                "name": "Milan Airport to City Center",
                "vehicle_category": "standard_sedan",
                "pickup_area": {
                    "type": "Polygon",
                    "coordinates": [[[9.0, 45.3], [9.1, 45.3], [9.1, 45.4], [9.0, 45.4], [9.0, 45.3]]]
                },
                "dropoff_area": {
                    "type": "Polygon",
                    "coordinates": [[[9.2, 45.5], [9.3, 45.5], [9.3, 45.6], [9.2, 45.6], [9.2, 45.5]]]
                },
                "price": 45.0,
                "bidirectional": True
            }
        ]
    
    def _default_min_fares(self) -> Dict[str, float]:
        """Default minimum fares for each vehicle category"""
        return {
            # Sedans
            "standard_sedan": 70.0,
            "premium_sedan": 80.0,
            "vip_sedan": 120.0,
            
            # Minivans
            "standard_minivan": 75.0,
            "xl_minivan": 80.0,
            "vip_minivan": 85.0,
            
            # Sprinters
            "sprinter_8_pax": 120.0,
            "sprinter_16_pax": 180.0,
            "sprinter_21_pax": 300.0,
            
            # Coach
            "coach_51_pax": 500.0
        }
    
    def _default_distance_based_min_fares(self) -> Dict[str, Dict[str, float]]:
        """Default distance-based minimum fares for each vehicle category"""
        return {
            # 0 to 5 km
            "0-5": {
                # Sedans
                "standard_sedan": 70.0,
                "premium_sedan": 80.0,
                "vip_sedan": 120.0,
                
                # Minivans - Updated for proper price hierarchy
                "standard_minivan": 80.0,  # Keep at 80
                "xl_minivan": 90.0,        # Update to 90
                "vip_minivan": 100.0,      # Update to 100
                
                # Sprinters
                "sprinter_8_pax": 120.0,
                "sprinter_16_pax": 180.0,
                "sprinter_21_pax": 300.0,
                
                # Coach
                "coach_51_pax": 500.0
            },
            # 5 to 20 km
            "5-20": {
                # Sedans
                "standard_sedan": 90.0,
                "premium_sedan": 100.0,
                "vip_sedan": 150.0,
                
                # Minivans - Updated for proper price hierarchy
                "standard_minivan": 100.0,
                "xl_minivan": 110.0,
                "vip_minivan": 120.0,
                
                # Sprinters
                "sprinter_8_pax": 190.0,
                "sprinter_16_pax": 240.0,
                "sprinter_21_pax": 360.0,
                
                # Coach
                "coach_51_pax": 600.0
            },
            # 20 to 50 km
            "20-50": {
                # Sedans
                "standard_sedan": 120.0,
                "premium_sedan": 130.0,
                "vip_sedan": 200.0,
                
                # Minivans - Updated for proper price hierarchy
                "standard_minivan": 125.0,
                "xl_minivan": 135.0,
                "vip_minivan": 145.0,
                
                # Sprinters
                "sprinter_8_pax": 220.0,
                "sprinter_16_pax": 300.0,
                "sprinter_21_pax": 400.0,
                
                # Coach
                "coach_51_pax": 800.0
            }
        }
        
    def validate_config(self) -> None:
        """Validate that the loaded configuration is sensible"""
        # Check that all vehicle categories have a positive rate
        for category, rate in self.vehicle_rates.items():
            if float(rate) <= 0:
                logger.error(f"Rate for {category} must be positive, got {rate}. Using default.")
                self.vehicle_rates[category] = self._default_vehicle_rates().get(category, 1.0)
        
        # Check that all zone multipliers are positive
        for zone, multiplier in self.zone_multipliers.items():
            if float(multiplier) <= 0:
                logger.error(f"Multiplier for zone {zone} must be positive, got {multiplier}. Using default.")
                self.zone_multipliers[zone] = self._default_zone_multipliers().get(zone, 1.0)
        
        # Validate minimum fares
        for category, min_fare in self.min_fares.items():
            if float(min_fare) <= 0:
                logger.error(f"Minimum fare for {category} must be positive, got {min_fare}. Using default.")
                self.min_fares[category] = self._default_min_fares().get(category, 10.0)
        
        # Check that all required configurations are present
        if not self.vehicle_rates:
            logger.critical("No vehicle rates configuration available. Using emergency defaults.")
            self.vehicle_rates = self._default_vehicle_rates()
            
        if not self.zone_multipliers:
            logger.critical("No zone multipliers configuration available. Using emergency defaults.")
            self.zone_multipliers = self._default_zone_multipliers()
        
        logger.info("Configuration validation completed successfully")