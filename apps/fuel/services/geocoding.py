
import hashlib

import requests
from django.conf import settings
from django.core.cache import cache

from apps.fuel.services.exceptions import GeocodingError
from apps.fuel.services.geo import Coordinate


class GoogleMapsGeocoder:
    """Geocode route start and finish addresses using Google Maps."""

    endpoint = "https://maps.googleapis.com/maps/api/geocode/json"
    cache_seconds = 60 * 60 * 24 * 30

    def geocode(self, address: str) -> Coordinate:
        normalized = address.strip()
        cache_key = "geocode:google:v1:" + hashlib.sha256(
            normalized.casefold().encode("utf-8")
        ).hexdigest()

        cached = cache.get(cache_key)
        if cached is not None:
            return Coordinate(
                latitude=cached[0],
                longitude=cached[1],
            )

        api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
        if not api_key:
            raise GeocodingError(
                "GOOGLE_MAPS_API_KEY is not configured."
            )

        try:
            response = requests.get(
                self.endpoint,
                params={
                    "address": normalized,
                    "components": "country:US",
                    "key": api_key,
                },
                timeout=settings.GOOGLE_MAPS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GeocodingError(
                "Google Maps geocoding request failed. "
                "Check API access, billing, and network connectivity."
            ) from exc

        if payload.get("status") != "OK" or not payload.get("results"):
            if payload.get("status") == "ZERO_RESULTS":
                raise GeocodingError(
                    f"Could not resolve the US location: {normalized}"
                )

            raise GeocodingError(
                "Google Maps could not resolve the location. "
                "Check the Geocoding API configuration and billing."
            )

        location = payload["results"][0]["geometry"]["location"]
        coordinate = Coordinate(
            latitude=float(location["lat"]),
            longitude=float(location["lng"]),
        )

        cache.set(
            cache_key,
            (coordinate.latitude, coordinate.longitude),
            self.cache_seconds,
        )
        return coordinate
