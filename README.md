# Airport Transfer Pricing API

A FastAPI-based pricing engine for calculating airport/city transfer prices.

## Features

- Check price based on pickup and dropoff coordinates
- Fixed price overrides for common routes
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
  "vehicle_category": "economy",
  "pickup_time": "2023-10-20T14:30:00"
}
```

Response:
```json
{
  "price": 45.5,
  "currency": "EUR"
}
```

## Configuration

All pricing configuration is stored in JSON files in the `config/` directory:

- `vehicle_rates.json`: Base rates per km for each vehicle category
- `zone_multipliers.json`: Multipliers for different geographical zones
- `time_multipliers.json`: Multipliers for different time periods (night, weekend)
- `surge_multipliers.json`: Special surge pricing for holidays and events
- `fixed_prices.json`: Fixed price overrides for specific routes

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

## License

MIT