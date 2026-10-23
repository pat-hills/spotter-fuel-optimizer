# Spotter AI — Fuel Route Optimizer

A Django REST API take-home implementation that returns a US driving route, fuel-stop recommendations, and an estimated fuel-purchase cost using the supplied assessment CSV.

## Design overview

- **API layer** validates HTTP input and formats HTTP responses only.
- **FuelPlanningService** coordinates geocoding, routing, station discovery, and optimization.
- **OsrmRoutingService** isolates the routing provider and requests the full GeoJSON route in one call per uncached route.
- **CensusGeocoder** isolates single-location geocoding and caches resolved start/finish locations.
- **FuelStation repository** owns the station query used by the planner.
- **Fuel optimization service** is a pure function with no Django, HTTP, or database dependencies.
- **PostgreSQL** stores fuel prices and geocoded station locations; Redis is used for shared caching when configured.

The route is returned as GeoJSON in the API response. A client can render it using Leaflet and OpenStreetMap tiles. The API does not generate a raster map image.

## Important data caveat

The assessment CSV has 8,151 rows and columns for truck-stop ID, name, address, city, state, rack ID, and retail price. It contains no latitude/longitude. Fuel-stop optimization cannot be geographically correct until coordinates are added.

`import_fuel_prices` loads the original records. `geocode_fuel_stations` uses the US Census Geocoder's batch endpoint. Truck-stop addresses written as highway exits may not resolve to an exact POI; unmatched rows are not silently treated as exact locations. Check the geocoding report and sample the results against a map before relying on the plan. For a production system, use a verified station-coordinate dataset or a geocoder with licensed POI coverage and retain match confidence/provenance. The batch geocoder is a one-time data-preparation step, not called for each trip.

## Fuel model and assumptions

- Maximum range: **500 miles** on a full tank.
- Fuel economy: **10 miles per gallon**.
- Implied tank capacity: **50 gallons**.
- Starting state: **full tank**.
- `fuel_purchase_cost_usd` includes purchases made at stops during the journey. The starting tank is treated as sunk fuel and its original cost is not included. Consequently, a trip no longer than the available starting range can legitimately have zero *in-trip purchases*. If the assessor expects total fuel consumed valued at market prices instead, define that accounting convention explicitly before comparing outputs.
- Stations are filtered to a route corridor and ordered by along-route mile marker. The initial implementation uses a greedy refuelling strategy: if a cheaper station is reachable within a full tank, purchase only enough to reach the next cheaper station; otherwise, fill as needed. It is designed for a fixed route and fixed tank size.
- Stations with missing coordinates or invalid prices are excluded. If the route cannot be completed using the available station coverage, the API returns HTTP 422 instead of inventing a fuel stop.
- Route distance comes from OSRM; route-mile station positions are approximated from the returned geometry. Station locations may also be approximate if the source address could not be geocoded exactly.

## Requirements

- Python 3.13+
- Docker and Docker Compose (recommended)
- The public OSRM and US Census geocoder endpoints must be reachable for uncached requests / initial data enrichment.

Django 6.1.2 is pinned as the current stable release at the time this project was prepared. Dependencies are pinned in `requirements.txt` for reproducibility.

## Run locally with Docker

1. Copy `.env.example` to `.env` and set a unique `DJANGO_SECRET_KEY` and database password for anything beyond local development.
2. Start services:

   ```bash
   docker compose up --build -d
   ```

3. Copy the provided CSV into the repository (or use its absolute path) and import it:

   ```bash
   docker compose exec api python manage.py import_fuel_prices /app/fuel-prices-for-be-assessment.csv
   ```

   If the CSV is not in the image/container, copy it first with `docker cp` or mount it as a volume. Example:

   ```bash
   docker cp fuel-prices-for-be-assessment.csv $(docker compose ps -q api):/tmp/fuel-prices.csv
   docker compose exec api python manage.py import_fuel_prices /tmp/fuel-prices.csv
   ```

4. Geocode the station data in one batch request:

   ```bash
   docker compose exec api python manage.py geocode_fuel_stations
   ```

   Review the matched/unmatched totals. Do not use the API for a route where station coverage is inadequate.

5. Submit a trip:

   ```bash
   curl -X POST http://localhost:8000/api/v1/fuel-plans/optimize/ \
     -H 'Content-Type: application/json' \
     -d '{"start":"Columbus, Ohio","finish":"Chicago, Illinois"}'
   ```

## Run locally without Docker

Create a virtual environment, install requirements, create a PostgreSQL database, set environment variables, then run:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
$env:DJANGO_SETTINGS_MODULE = "config.settings.development" # PowerShell
python manage.py migrate
python manage.py runserver
```

Import and geocode the CSV using the commands above. Use `.env.example` as the configuration reference.

## API contract

`POST /api/v1/fuel-plans/optimize/`

Request:

```json
{
  "start": "Columbus, Ohio",
  "finish": "Chicago, Illinois"
}
```

Successful response includes:

- `route`: GeoJSON `Feature` containing route geometry suitable for a map client.
- `route_distance_miles` and `route_duration_seconds`.
- `stops`: ordered fuel stops with price, route mile, purchase gallons, cost, and fuel level on arrival/departure.
- `fuel_purchase_cost_usd`: estimated cost of fuel purchased during the journey.
- `estimated_fuel_consumed_gallons`: route distance divided by 10 MPG.
- `assumptions`, `map_attribution`, and `station_location_quality`.

Errors use a stable envelope. Examples include `400` for invalid input, `422` when a location cannot be resolved or fuel coverage is insufficient, and `502` when the routing provider is unavailable.

## External service calls and latency

- One Census geocoding request per uncached trip endpoint (start and finish; cached for 30 days).
- One OSRM route request per uncached origin/destination pair (cached for one hour by default).
- Fuel station lookup and optimization are local database / application operations; no per-stop routing calls are made.
- Configure Redis via `CACHE_URL` in deployed environments. The local-memory cache is only appropriate for a single-process development setup.
- Public OSRM is a best-effort demo service with usage restrictions and no uptime guarantee. It is appropriate for an assessment demo, not a production SLA. Keep the provider adapter and deploy a managed or self-hosted routing service for production traffic. Display OpenStreetMap attribution.

## Tests and quality checks

```bash
pytest
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
```

Tests cover the optimizer's core behaviors, geographic distance helpers, and request validation. Provider calls should be mocked in integration tests when expanding this project. Before submission, run the tests against a real PostgreSQL instance and add a route-planning integration test with a fixed GeoJSON fixture.

## Production hardening checklist

- Set a high-entropy secret key; set `DJANGO_DEBUG=false`; configure allowed hosts and HTTPS.
- Use managed PostgreSQL, Redis, TLS, backups, connection pooling, and database monitoring.
- Add authentication / per-customer quotas if the API is not intentionally public.
- Add provider circuit breakers, bounded retries, request correlation IDs, metrics, and structured logs.
- Add idempotent data refreshes and source timestamps for changing fuel prices.
- Validate geocoding accuracy and station freshness; city-level coordinates are not precise enough for final production recommendations.
- For materially larger station datasets, replace float bounding-box scans with PostGIS `geography` columns and a GiST index. Benchmark representative cross-country routes and concurrent traffic before claiming a particular scale.
- Add CI that runs formatting, linting, tests, migration checks, dependency vulnerability scans, and container image scans.

## Map display

The API response includes GeoJSON. A minimal frontend can render `response.route.geometry` as a polyline and add markers for each item in `response.stops`. Use a maintained Leaflet release and include visible OpenStreetMap attribution. Keeping visualization on the client avoids coupling the API to a map-rendering framework.

## Postman demo

Import `postman/Spotter-Fuel-Optimizer.postman_collection.json` into Postman. Start the API and set the collection variable `base_url` to the deployed URL or `http://localhost:8000`. The collection includes a Columbus-to-Chicago request and basic response assertions. The request succeeds only after the fuel CSV has been imported and station geocoding has produced adequate route coverage.

## Suggested five-minute walkthrough

1. **0:00–0:30** — State the problem, fixed assumptions, and API contract.
2. **0:30–1:30** — Show the project structure: API view/serializer, planning service, routing adapter, station repository, pure optimizer.
3. **1:30–2:15** — Explain the CSV import and coordinate-enrichment workflow, including the no-coordinate data limitation.
4. **2:15–3:45** — Send the Postman request; inspect GeoJSON route, selected fuel stops, per-stop gallons/cost, and assumptions.
5. **3:45–4:30** — Explain caching: route response and full plan are cached; no routing call is made per fuel stop.
6. **4:30–5:00** — Mention tests, deployment configuration, geocoding accuracy limitations, and the production upgrade path (PostGIS and a managed/self-hosted routing provider).

## Push to GitHub

Create an empty repository on GitHub, then from this project directory run:

```bash
git init
git add .
git commit -m "Build fuel route optimization API"
git branch -M main
git remote add origin https://github.com/<your-account>/<repository-name>.git
git push -u origin main
```

Do not commit `.env` or secrets. Keep the assessment CSV only if the hiring team permits redistributing the supplied file in the repository.
