# Airport Transfer Pricing API

A FastAPI-based pricing engine for calculating airport/city transfer prices.

## Features

- Check price based on pickup and dropoff coordinates
- Return prices for all vehicle categories as an array
- Support for one-way and round trip options
- Fixed price overrides for common routes
- Distance-based minimum fares
- Dynamic pricing based on distance, zones, and time
- Spatial indexing for efficient zone lookups
- Support for time-based pricing (night/weekend/holiday rates)
- Price rounding to the nearest 10 EUR
- Supabase integration for pricing configuration
- Multiple routing providers (Google Maps, Mapbox) with fallbacks

## API Endpoints

### Check Price

```
POST /check-price
```

Request body:
```json
{
  "pickup_lat": 41.8,
  "pickup_lng": 12.25,
  "dropoff_lat": 41.9,
  "dropoff_lng": 12.5,
  "pickup_time": "2023-10-20T14:30:00",
  "trip_type": "1"
}
```

Response:
```json
{
  "prices": [
    {
      "category": "standard_sedan",
      "raw_price": 65,
      "currency": "EUR",
      "price": 70
    },
    {
      "category": "premium_sedan",
      "raw_price": 70,
      "currency": "EUR",
      "price": 70
    },
    {
      "category": "vip_sedan",
      "raw_price": 120,
      "currency": "EUR",
      "price": 120
    }
  ],
  "details": {
    "pickup_time": "2023-10-20T14:30:00",
    "pickup_location": {
      "lat": 41.8,
      "lng": 12.25
    },
    "dropoff_location": {
      "lat": 41.9,
      "lng": 12.5
    },
    "trip_type": "one-way"
  }
}
```

Example for round trip:
```json
{
  "pickup_lat": 41.8,
  "pickup_lng": 12.25,
  "dropoff_lat": 41.9,
  "dropoff_lng": 12.5,
  "pickup_time": "2023-10-20T14:30:00",
  "trip_type": "2"
}
```

### Get Configuration

```
GET /config
```

Response:
```json
{
  "vehicle_categories": [
    "standard_sedan",
    "premium_sedan",
    "vip_sedan",
    "standard_minivan",
    "xl_minivan",
    "vip_minivan",
    "sprinter_8_pax",
    "sprinter_16_pax",
    "sprinter_21_pax",
    "coach_51_pax"
  ],
  "currency": "EUR",
  "zones": [
    "RM",
    "MI",
    "FI",
    "DEFAULT"
  ]
}
```

### Refresh Configuration

```
POST /refresh-config
```

Response:
```json
{
  "status": "success",
  "message": "Configuration refreshed"
}
```

## Configuration

Configuration can be stored in:

1. **Supabase Database** (primary source if enabled)
2. **JSON files** (fallback if Supabase is disabled or unavailable)

### Supabase Tables

The pricing engine uses the following tables in Supabase:

- `vehicle_base_prices`: Base rates per km for each vehicle category
- `zone_multipliers`: Multipliers for different geographical zones
- `zones`: Geographical zones with province codes (prov_acr)
- `fixed_routes`: Fixed price overrides for specific routes

### Local Configuration Files

Fallback JSON files in the `config/` directory:

- `vehicle_rates.json`: Base rates per km for each vehicle category
- `zone_multipliers.json`: Multipliers for different geographical zones
- `time_multipliers.json`: Multipliers for different time periods (night, weekend)
- `fixed_prices.json`: Fixed price overrides for specific routes
- `min_fares.json`: Minimum fare for each vehicle category
- `distance_based_min_fares.json`: Minimum fares based on distance ranges

## Supabase Setup

1. Set the environment variables:
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_SERVICE_KEY`: Your Supabase service role API key

2. Run the setup script to create necessary tables and functions:
   ```
   python setup_supabase.py
   ```

3. Use the admin panel to manage pricing configuration:
   ```
   streamlit run admin_panel_example.py
   ```

## Environment Variables

- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_SERVICE_KEY`: Supabase service role API key
- `GOOGLE_MAPS_API_KEY`: Google Maps API key for routing
- `MAPBOX_API_KEY`: Mapbox API key (fallback routing)
- `DEFAULT_CURRENCY`: Currency for prices (default: EUR)
- `GEOJSON_PATH`: Path to GeoJSON file with zone data

## Development

### Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

### Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up environment variables
4. Run the API: `python main.py`

### Docker

Build and run with Docker:

```
docker build -t transfer-pricing-api .
docker run -p 8080:8080 -e SUPABASE_URL=your-url -e SUPABASE_SERVICE_KEY=your-key -e GOOGLE_MAPS_API_KEY=your-key transfer-pricing-api
```

## Deployment

This API is designed to be deployed on Google Cloud Run.

1. Build the Docker image
2. Push to Google Container Registry
3. Deploy to Cloud Run with appropriate environment variables