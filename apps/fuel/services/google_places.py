
import requests
from django.conf import settings
from django.core.cache import cache

from apps.fuel.services.exceptions import GeocodingError


class GooglePlacesGeocoder:
    """Search Google Places for fuel-station location candidates."""

    endpoint = "https://places.googleapis.com/v1/places:searchText"
    cache_seconds = 60 * 60 * 24 * 30

    def search_station(self, station) -> list[dict]:
        """Return candidate places without changing the station record."""
        query_parts = [
            station.name,
            station.address,
            station.city,
            station.state,
            "USA",
        ]
        query = ", ".join(
            part.strip()
            for part in query_parts
            if part and part.strip()
        )

        cache_key = f"google-places:v1:{query.casefold()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        api_key = settings.GOOGLE_MAPS_API_KEY
        if not api_key:
            raise GeocodingError(
                "GOOGLE_MAPS_API_KEY is not configured."
            )

        try:
            response = requests.post(
                self.endpoint,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": (
                        "places.id,"
                        "places.displayName,"
                        "places.formattedAddress,"
                        "places.location,"
                        "places.types"
                    ),
                },
                json={
                    "textQuery": query,
                    "pageSize": 5,
                },
                timeout=settings.GOOGLE_MAPS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            places = response.json().get("places", [])

        except (requests.RequestException, ValueError) as exc:
            raise GeocodingError(
                "Google Places search failed. "
                "Check API access, billing, and network connectivity."
            ) from exc

        candidates = []

        for place in places:
            location = place.get("location")
            if not location:
                continue

            try:
                latitude = float(location["latitude"])
                longitude = float(location["longitude"])
            except (KeyError, TypeError, ValueError):
                continue

            if not (
                -90 <= latitude <= 90
                and -180 <= longitude <= 180
            ):
                continue

            display_name = place.get("displayName", {})
            candidates.append({
                "place_id": place.get("id", ""),
                "name": display_name.get("text", ""),
                "address": place.get("formattedAddress", ""),
                "latitude": latitude,
                "longitude": longitude,
                "types": place.get("types", []),
            })

        # Cache successful searches, including searches with no results.
        cache.set(cache_key, candidates, self.cache_seconds)
        return candidates
