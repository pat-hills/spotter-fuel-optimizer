# Spotter AI — Fuel Route Optimizer

A Django REST API that returns a US driving route, recommends fuel stops along the route, and estimates fuel-purchase and total trip fuel costs using fuel-price data.

## Design overview

- **API layer:** Validates HTTP input and formats API responses.
- **FuelPlanningService:** Coordinates geocoding, routing, station discovery, and fuel optimization.
- **GoogleMapsGeocoder:** Uses the Google Maps Geocoding API to resolve trip start and finish addresses and caches resolved coordinates.
- **GooglePlacesGeocoder:** Uses Google Places Text Search to find candidate fuel-station locations for review. Candidate results are not automatically treated as verified station coordinates.
- **OsrmRoutingService:** Uses OSRM to obtain driving distance, duration, and full GeoJSON route geometry in one request for each uncached route.
- **Census batch geocoder:** Enriches fuel-station coordinates using the US Census Geocoder during data preparation.
- **FuelStation repository:** Provides database queries for fuel stations near the route corridor.
- **Fuel optimization service:** Implements the refuelling logic independently of Django, HTTP requests, and database operations.
- **PostgreSQL:** Stores fuel prices and station locations. Redis provides shared caching when configured.

The API returns route geometry as GeoJSON. A client can render the route using Leaflet and OpenStreetMap tiles. The API does not generate a raster map image. Google Maps is used for geocoding and station candidate searches, not for calculating the road route.

## Important data caveat

The assessment CSV contains 8,151 rows with truck-stop ID, name, address, city, state, rack ID, and retail price. It does not include latitude or longitude. Fuel-stop recommendations depend on adding usable coordinates to the station records.

The `import_fuel_prices` command imports the original records. The `geocode_fuel_stations` command uses the US Census Geocoder's batch endpoint to enrich station coordinates.

Truck-stop addresses that use highway exits or other non-standard address formats may not resolve to the exact station. Unmatched or ambiguous records must not be treated as verified locations. Review the geocoding report and sample station coordinates against a map before relying on a route plan.

The Google Places search and station-review utilities can help identify candidate locations. Candidate matches should be reviewed before being approved as station coordinates.

For production use, prefer a verified station-coordinate dataset or an appropriately licensed geocoding provider. Retain coordinate provenance, match status, and review information.

Bulk geocoding is a data-preparation operation; it is not performed for every trip.

## Fuel model and assumptions

- **Maximum vehicle range:** 500 miles on a full tank.
- **Fuel economy:** 10 miles per gallon.
- **Implied tank capacity:** 50 gallons.
- **Starting fuel:** A full 50-gallon tank.
- **Arrival reserve:** The planner targets a 2-gallon fuel reserve.
- **Planned refuelling legs:** The optimizer limits planned legs to 480 miles to preserve the arrival reserve under the stated fuel-economy assumption.

`fuel_purchase_cost_usd` represents the estimated cost of fuel purchased at stops during the trip. Fuel already in the starting tank is not included in that purchase total.

`estimated_total_trip_fuel_cost_usd` is a separate estimate that values all fuel consumed using the average price of available route candidates, or the dataset-wide average if route-candidate prices are unavailable. It is an estimate, not a sum of the selected stop purchases.

The planner filters stations to a corridor around the route and calculates each candidate's approximate position along the route. It considers station prices and reachability when selecting fuel stops.

Stations with missing coordinates or invalid prices are excluded. If the available station coverage cannot support a feasible trip plan, the API returns an error rather than inventing a fuel stop.

Route distance and duration come from OSRM. Station positions are approximated from the returned route geometry, and station coordinates may be approximate when an address cannot be geocoded precisely.

## Requirements

- Python 3.13 or later.
- Docker and Docker Compose (recommended).
- PostgreSQL.
- Redis (optional; local-memory caching is used when Redis is not configured).
- Google Maps Platform API key for uncached trip-address geocoding and Google Places station searches.
- Network access to the US Census Geocoder for initial station-coordinate enrichment.
- Network access to OSRM for uncached routes.

Dependencies are pinned in `requirements.txt`.

## External services

### Google Maps Platform

The application uses:

- **Geocoding API:** Resolves the trip's start and finish addresses.
- **Places API (New):** Searches for candidate fuel-station locations during the station review workflow.

Configure the following environment variables:

```dotenv
GOOGLE_MAPS_API_KEY=replace-with-your-google-maps-api-key
GOOGLE_MAPS_TIMEOUT_SECONDS=10
```

Enable the relevant Google Maps Platform APIs and billing in Google Cloud. Restrict the API key to the required APIs and any applicable restrictions.

Keep the real API key in your local `.env` file or deployment secret store. Never commit the real key to GitHub.

For Docker Compose, ensure the Google Maps variables are passed into the `api` container through its environment configuration. Do not rely on including a local `.env` file in the Docker image.

### US Census Geocoder

The batch geocoder enriches fuel-station coordinates during data preparation. Set `GEOCODING_USER_AGENT` to identify the application and provide a valid contact email, as required by the command.

### OSRM

OSRM supplies driving routes, distances, durations, and GeoJSON geometry. Route responses are cached to reduce repeated routing requests.

The public OSRM service is suitable for an assessment demonstration, not a production service-level guarantee. A production deployment should evaluate a managed or self-hosted routing provider.

## Run locally with Docker

1. Copy `.env.example` to `.env` and configure the application settings. Set a unique `DJANGO_SECRET_KEY`, an appropriate database password, the Google Maps API key, and a valid geocoding contact address.

2. Make sure the Google Maps environment variables are passed to the `api` service in `docker-compose.yml`. The relevant entries under `api.environment` are:

   ```yaml
   GOOGLE_MAPS_API_KEY: ${GOOGLE_MAPS_API_KEY:-}
   GOOGLE_MAPS_TIMEOUT_SECONDS: ${GOOGLE_MAPS_TIMEOUT_SECONDS:-10}
   ```

3. Start the services:

   ```bash
   docker compose up --build -d
   ```

4. Obtain the assessment CSV according to the assessment's distribution rules. Place it in the project directory or copy it into the running API container. Import it into the database:

   ```bash
   docker compose exec api python manage.py import_fuel_prices /app/fuel-prices-for-be-assessment.csv
   ```

   If the CSV is not available inside the container, copy it first:

   ```bash
   docker cp fuel-prices-for-be-assessment.csv $(docker compose ps -q api):/tmp/fuel-prices.csv

   docker compose exec api python manage.py import_fuel_prices /tmp/fuel-prices.csv
   ```

5. Enrich the station coordinates:

   ```bash
   docker compose exec api python manage.py geocode_fuel_stations
   ```

   Review the matched, unmatched, and ambiguous results. Do not assume the dataset has sufficient verified station coverage for every route.

6. Submit a trip request:

   ```bash
   curl -X POST http://localhost:8000/api/v1/fuel-plans/optimize/ \
     -H 'Content-Type: application/json' \
     -d '{"start":"Columbus, Ohio","finish":"Chicago, Illinois"}'
   ```

## Run locally without Docker

Create a virtual environment, install the dependencies, configure PostgreSQL, and set the environment variables.

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, configure the settings described above, and set the Django settings module.

Windows PowerShell:

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.settings.development"
```

Run the database migrations and start Django:

```bash
python manage.py migrate
python manage.py runserver
```

Import the assessment CSV and enrich the station coordinates using the management commands described in the Docker instructions.

## API contract

**Endpoint:** `POST /api/v1/fuel-plans/optimize/`

Request:

```json
{
  "start": "Columbus, Ohio",
  "finish": "Chicago, Illinois"
}
```

The successful response includes:

- `start` and `finish`: Requested addresses and resolved coordinates.
- `route`: A GeoJSON `Feature` containing route geometry.
- `route_distance_miles` and `route_duration_seconds`: Route distance and estimated driving duration.
- `stops`: Ordered fuel stops, including station coordinates, price per gallon, route mile, distance from the route, gallons to purchase, estimated purchase cost, and fuel on arrival and departure.
- `fuel_purchase_cost_usd`: Estimated cost of fuel purchased at the recommended stops.
- `estimated_fuel_consumed_gallons`: Estimated fuel consumption based on route distance and 10 MPG.
- `estimated_total_trip_fuel_cost_usd`: Estimated cost of all fuel consumed, using the documented average-price method.
- `assumptions`: The fuel model and planning assumptions.
- `map_attribution`: Attribution information for the routing data.
- `station_location_quality`: A description of station-location accuracy limitations.

Errors use a consistent API error response. Typical status codes include `400` for invalid input, `422` when a location cannot be resolved or station coverage is insufficient, and `502` when a routing provider is unavailable.

## External service calls and caching

- **Google Maps Geocoding API:** Resolves uncached trip endpoints. Successful geocoding results are cached for 30 days.
- **Google Places API (New):** Searches for fuel-station candidates as part of the location-review workflow. Successful searches are cached for 30 days.
- **US Census Geocoder:** Used for batch enrichment of fuel-station coordinates during data preparation.
- **OSRM:** Makes one route request for each uncached origin/destination pair by default. Route caching is configured through `ROUTING_CACHE_SECONDS`, which defaults to one hour.
- **Fuel station discovery and optimization:** Performed by the application and database; the planner does not make an individual routing request for every fuel stop.

Configure Redis using `CACHE_URL` in deployed environments. Local-memory caching is appropriate only for a single-process development setup.

## Tests and quality checks

Run the tests:

```bash
python -m pytest -q
```

Run Ruff:

```bash
ruff check .
```

Check Django configuration:

```bash
python manage.py check
```

Check for uncommitted migration changes:

```bash
python manage.py makemigrations --check --dry-run
```

The test suite covers core optimizer behavior, geographic distance helpers, and API request validation. Provider interactions should be mocked in automated tests where appropriate, and route-planning integration tests should use fixed route fixtures for deterministic results.

Before deploying, run the tests against PostgreSQL and validate the end-to-end flow using representative route data.

## Production hardening

Before using this application in production:

- Set a high-entropy Django secret key, disable debug mode, configure allowed hosts, and enforce HTTPS.
- Use managed PostgreSQL and Redis, database backups, TLS, connection pooling, and monitoring.
- Restrict API access or introduce authentication and customer-specific rate limits where appropriate.
- Add provider circuit breakers, bounded retries, request correlation IDs, metrics, and structured logs.
- Add idempotent data-refresh jobs and source timestamps for fuel prices.
- Validate station coordinates and data freshness. City-level approximations are not precise enough for reliable production recommendations.
- Consider PostGIS geography columns and GiST indexes for larger station datasets. Benchmark representative routes and concurrent traffic before making scalability claims.
- Add continuous integration for linting, tests, migration checks, dependency vulnerability checks, and container image scans.

## Map display

The API returns route geometry as GeoJSON. A client can render `response.route.geometry` as a polyline and add markers for each item in `response.stops`.

Use a maintained Leaflet release and display visible OpenStreetMap attribution when using OpenStreetMap tiles. Map visualization is kept separate from the API so clients can render the route without coupling the backend to a map-rendering framework.

## Postman demo

Import `postman/Spotter-Fuel-Optimizer.postman_collection.json` into Postman.

Set the collection variable `base_url` to the deployed API URL or `http://localhost:8000`.

The collection includes a Columbus-to-Chicago request and basic response assertions. The request succeeds only when the database has been populated with fuel-price data and station geocoding has provided sufficient route coverage.