# Airport Transfer Pricing API

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
