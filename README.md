# Airport Transfer Pricing API

A FastAPI-based pricing engine for calculating airport/city transfer prices.

## Features

- Check price based on pickup and dropoff coordinates
- Return prices for all vehicle categories as an array
- Fixed price overrides for common routes
- Distance-based minimum fares
- Dynamic pricing based on distance, zones, and time
- Spatial indexing for efficient zone lookups
- Support for time-based pricing (night/weekend/holiday rates)

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
  "pickup_time": "2023-10-20T14:30:00"
}
```

Response:
```json
{
  "prices": [
    {
      "category": "standard_sedan",
      "price": 65,
      "currency": "EUR"
    },
    {
      "category": "premium_sedan",
      "price": 70,
      "currency": "EUR"
    },
    {
      "category": "vip_sedan",
      "price": 120,
      "currency": "EUR"
    },
    {
      "category": "standard_minivan",
      "price": 75,
      "currency": "EUR"
    },
    {
      "category": "xl_minivan",
      "price": 80,
      "currency": "EUR"
    },
    {
      "category": "vip_minivan",
      "price": 85,
      "currency": "EUR"
    },
    {
      "category": "sprinter_8_pax",
      "price": 120,
      "currency": "EUR"
    },
    {
      "category": "sprinter_16_pax",
      "price": 180,
      "currency": "EUR"
    },
    {
      "category": "sprinter_21_pax",
      "price": 300,
      "currency": "EUR"
    },
    {
      "category": "coach_51_pax",
      "price": 500,
      "currency": "EUR"
    }
  ],
  "selected_category": null,
  "details": {
    "pickup_time": "2023-10-20T14:30:00",
    "pickup_location": {
      "lat": 41.8,
      "lng": 12.25
    },
    "dropoff_location": {
      "lat": 41.9,
      "lng": 12.5
    }
  }
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

## Configuration

All pricing configuration is stored in JSON files in the `config/` directory:

- `vehicle_rates.json`: Base rates per km for each vehicle category
- `zone_multipliers.json`: Multipliers for different geographical zones
- `time_multipliers.json`: Multipliers for different time periods (night, weekend)
- `surge_multipliers.json`: Special surge pricing for holidays and events
- `fixed_prices.json`: Fixed price overrides for specific routes
- `min_fares.json`: Minimum fare for each vehicle category
- `distance_based_min_fares.json`: Minimum fares based on distance ranges

## Development

### Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

### Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run the API: `python main.py`

### Docker

Build and run with Docker:

```
docker build -t transfer-pricing-api .
docker run -p 8080:8080 transfer-pricing-api
```

## Deployment

This API is designed to be deployed on Google Cloud Run.

1. Build the Docker image
2. Push to Google Container Registry
3. Deploy to Cloud Run