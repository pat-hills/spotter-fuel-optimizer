
from decimal import Decimal, ROUND_HALF_UP
from math import cos, radians
import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.db.models import Avg

from apps.fuel.models import FuelStation
from apps.fuel.repositories.stations import stations_near_bounds
from apps.fuel.services.exceptions import RoutingProviderError
from apps.fuel.services.geo import (
    Coordinate,
    RoutePoint,
    build_route_points,
    project_to_route,
)
from apps.fuel.services.optimizer import (
    CandidateStation,
    optimize_fuel_plan,
)

MPG = 10.0
MONEY = Decimal("0.01")


def _route_bounds(
    points: list[RoutePoint],
) -> tuple[float, float, float, float]:
    latitudes = [point.coordinate.latitude for point in points]
    longitudes = [point.coordinate.longitude for point in points]
    average_latitude = sum(latitudes) / len(latitudes)

    lat_margin = 0.16
    lon_margin = min(
        1.5,
        0.16 / max(0.2, abs(cos(radians(average_latitude)))),
    )

    return (
        min(latitudes) - lat_margin,
        max(latitudes) + lat_margin,
        min(longitudes) - lon_margin,
        max(longitudes) + lon_margin,
    )


class FuelPlanningService:
    def __init__(self, routing_service, geocoder):
        self.routing_service = routing_service
        self.geocoder = geocoder

    def plan(self, start_address: str, finish_address: str) -> dict:
        data_version = cache.get("fuel-data-version", "initial")
        cache_payload = json.dumps(
            [
                start_address.strip().lower(),
                finish_address.strip().lower(),
                data_version,
            ],
            separators=(",", ":"),
        )
        plan_cache_key = "fuel-plan:v1:" + hashlib.sha256(
            cache_payload.encode()
        ).hexdigest()

        cached_plan = cache.get(plan_cache_key)
        if cached_plan is not None:
            return cached_plan

        start = self.geocoder.geocode(start_address)
        finish = self.geocoder.geocode(finish_address)
        route = self.routing_service.get_route(start, finish)

        geometry_coordinates = route["geometry"].get("coordinates", [])
        if len(geometry_coordinates) < 2:
            raise RoutingProviderError(
                "Routing provider returned insufficient route geometry."
            )

        # Sample the route polyline for efficient station-corridor matching.
        sample_step = max(1, len(geometry_coordinates) // 250)
        sampled = geometry_coordinates[::sample_step]

        if sampled[-1] != geometry_coordinates[-1]:
            sampled.append(geometry_coordinates[-1])

        route_points = build_route_points(sampled)
        geometry_distance = route_points[-1].distance_miles

        if geometry_distance > 0:
            scale = route["distance_miles"] / geometry_distance
            route_points = [
                RoutePoint(
                    point.coordinate,
                    point.distance_miles * scale,
                )
                for point in route_points
            ]

        bounds = _route_bounds(route_points)
        station_rows = stations_near_bounds(
            *bounds,
            limit=settings.MAX_ROUTE_STATIONS,
        )

        candidates = []

        for station in station_rows:
            coordinate = Coordinate(
                station.latitude,
                station.longitude,
            )
            distance_from_route, route_mile = project_to_route(
                coordinate,
                route_points,
            )

            if distance_from_route > settings.MAX_STATION_DISTANCE_MILES:
                continue

            candidates.append(
                CandidateStation(
                    station_id=station.pk,
                    name=station.name,
                    address=station.address,
                    city=station.city,
                    state=station.state,
                    latitude=station.latitude,
                    longitude=station.longitude,
                    price_per_gallon=station.price_per_gallon,
                    route_mile=route_mile,
                    distance_from_route_miles=distance_from_route,
                    location_precision=station.geocode_status,
                )
            )

        route_distance = route["distance_miles"]
        plan = optimize_fuel_plan(route_distance, candidates)

        # Estimate fuel consumed and the total cost of fuel for the journey.
        gallons_consumed = route_distance / MPG

        route_prices = [
            station.price_per_gallon
            for station in candidates
            if station.price_per_gallon > 0
        ]

        if route_prices:
            average_price = (
                sum(route_prices, Decimal("0")) / len(route_prices)
            )
            price_method = "route_station_average"
        else:
            average_price = FuelStation.objects.filter(
                price_per_gallon__gt=0
            ).aggregate(
                average=Avg("price_per_gallon")
            )["average"]
            price_method = "dataset_wide_average"

        if average_price is not None:
            estimated_total = (
                Decimal(str(gallons_consumed)) * average_price
            ).quantize(MONEY, rounding=ROUND_HALF_UP)

            price_estimation = {
                "method": price_method,
                "note": (
                    "Estimated total fuel cost for the journey. Uses the "
                    "average price of available route candidates, or the "
                    "dataset-wide average when route prices are unavailable."
                ),
            }
            average_price_output = str(
                average_price.quantize(Decimal("0.001"))
            )
            estimated_total_output = str(estimated_total)
        else:
            price_estimation = {
                "method": "unavailable",
                "note": "No usable fuel prices were found in the dataset.",
            }
            average_price_output = None
            estimated_total_output = None

        plan.update(
            {
                "start": {
                    "address": start_address,
                    "latitude": start.latitude,
                    "longitude": start.longitude,
                },
                "finish": {
                    "address": finish_address,
                    "latitude": finish.latitude,
                    "longitude": finish.longitude,
                },
                "route": {
                    "type": "Feature",
                    "properties": {
                        "provider": "OSRM",
                        "distance_miles": round(route_distance, 2),
                    },
                    "geometry": route["geometry"],
                },
                "route_duration_seconds": round(
                    route["duration_seconds"]
                ),
                "map_attribution": (
                     "OpenStreetMap contributors; routing by OSRM"
                ),
                "candidate_station_count": len(candidates),
                "station_location_quality": (
                    "Station coordinates may be city-level approximations "
                    "where the source address could not be geocoded exactly."
                ),
                "estimated_fuel_consumed_gallons": round(
                    gallons_consumed, 2
                ),
                "estimated_total_trip_fuel_cost_usd": (
                    estimated_total_output
                ),
                "average_fuel_price_usd_per_gallon": average_price_output,
                "fuel_price_estimation": price_estimation,
            }
        )

        cache.set(
            plan_cache_key,
            plan,
            settings.ROUTING_CACHE_SECONDS,
        )

        return plan
