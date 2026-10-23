
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.fuel.models import FuelStation, StationGeocodeReview
from apps.fuel.services.exceptions import GeocodingError
from apps.fuel.services.google_places import GooglePlacesGeocoder


class Command(BaseCommand):
    help = "Find Google Places candidates for unresolved fuel stations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum number of stations to search (default: 10).",
        )
        parser.add_argument(
            "--station-id",
            type=int,
            help="Process one specific station instead of a batch.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        station_id = options["station_id"]

        if limit < 1:
            raise CommandError("--limit must be greater than zero.")

        queryset = FuelStation.objects.filter(
            geocode_status__in=["pending", "unmatched", "ambiguous"],
            latitude__isnull=True,
            longitude__isnull=True,
        ).order_by("id")

        if station_id is not None:
            queryset = queryset.filter(pk=station_id)
            limit = 1

        stations = list(queryset[:limit])

        if not stations:
            self.stdout.write("No unresolved stations found.")
            return

        geocoder = GooglePlacesGeocoder()
        processed = 0
        candidate_count = 0
        failed = 0

        for station in stations:
            # Avoid repeating searches when candidates are already awaiting review.
            has_pending_review = StationGeocodeReview.objects.filter(
                station=station,
                status=StationGeocodeReview.Status.PENDING,
            ).exists()

            if has_pending_review:
                self.stdout.write(
                    f"Skipping station #{station.pk}: candidates "
                    "are already awaiting review."
                )
                continue

            try:
                candidates = geocoder.search_station(station)
            except GeocodingError as exc:
                failed += 1
                self.stderr.write(
                    f"Station #{station.pk} failed: {exc}"
                )
                continue

            with transaction.atomic():
                for number, candidate in enumerate(candidates, start=1):
                    StationGeocodeReview.objects.update_or_create(
                        station=station,
                        candidate_number=number,
                        defaults={
                            "provider": "google_places",
                            "provider_place_id": candidate.get(
                                "place_id", ""
                            ),
                            "name": candidate.get("name", ""),
                            "address": candidate.get("address", ""),
                            "latitude": candidate["latitude"],
                            "longitude": candidate["longitude"],
                            "types": candidate.get("types", []),
                            "status": StationGeocodeReview.Status.PENDING,
                            "reviewed_at": None,
                        },
                    )

            processed += 1
            candidate_count += len(candidates)

            self.stdout.write(
                f"Station #{station.pk}: {station.name} — "
                f"{len(candidates)} candidate(s) saved for review."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Finished. Searched {processed} station(s), "
                f"saved {candidate_count} candidate(s), "
                f"failed {failed} search(es)."
            )
        )
