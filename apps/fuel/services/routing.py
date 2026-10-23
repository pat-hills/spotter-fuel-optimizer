import hashlib
import requests
from django.conf import settings
from django.core.cache import cache
from apps.fuel.services.exceptions import RoutingProviderError
from apps.fuel.services.geo import Coordinate

class OsrmRoutingService:
    """Thin adapter around OSRM; one request returns distance and map geometry."""
    def get_route(self, start: Coordinate, finish: Coordinate) -> dict:
        key_payload = f"{start.latitude:.5f},{start.longitude:.5f}:{finish.latitude:.5f},{finish.longitude:.5f}"
        cache_key = "route:v1:" + hashlib.sha256(key_payload.encode()).hexdigest()
        cached = cache.get(cache_key)
        if cached:
            return cached
        url = (f"{settings.ROUTING_BASE_URL.rstrip('/')}/route/v1/driving/"
               f"{start.longitude},{start.latitude};{finish.longitude},{finish.latitude}")
        try:
            response = requests.get(url, params={"overview": "full", "geometries": "geojson", "steps": "false"},
                                    headers={"User-Agent": "spotter-fuel-optimizer-assessment/1.0"},
                                    timeout=settings.ROUTING_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RoutingProviderError("The routing provider is temporarily unavailable.") from exc
        routes = payload.get("routes", [])
        if payload.get("code") != "Ok" or not routes:
            raise RoutingProviderError("No drivable route was found between these locations.")
        route = {"distance_miles": routes[0]["distance"] / 1609.344,
                 "duration_seconds": routes[0].get("duration", 0),
                 "geometry": routes[0]["geometry"]}
        cache.set(cache_key, route, settings.ROUTING_CACHE_SECONDS)
        return route
