
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.fuel.models import FuelStation, StationGeocodeReview


class Command(BaseCommand):
    help = "Review saved Google Places candidates for a fuel station."

    def add_arguments(self, parser):
        parser.add_argument(
            "--station-id",
            type=int,
            required=True,
            help="Database ID of the station to review.",
        )
        parser.add_argument(
            "--approve",
            type=int,
            help="Candidate number to approve, starting at 1.",
        )

    def handle(self, *args, **options):
        station_id = options["station_id"]
        candidate_number = options["approve"]

        try:
            station = FuelStation.objects.get(pk=station_id)
        except FuelStation.DoesNotExist as exc:
            raise CommandError(
                f"Fuel station {station_id} was not found."
            ) from exc

        self.stdout.write(
            f"Station #{station.pk}: {station.name}\n"
            f"CSV address: {station.address}, "
            f"{station.city}, {station.state}\n"
            f"Current status: {station.geocode_status}"
        )

        if candidate_number is not None:
            self._approve(station_id, candidate_number)
            return

        candidates = StationGeocodeReview.objects.filter(
            station_id=station_id,
            status=StationGeocodeReview.Status.PENDING,
        ).order_by("candidate_number")

        if not candidates.exists():
            self.stdout.write(
                self.style.WARNING(
                    "No saved candidates are awaiting review. "
                    "Run geocode_stations_google for this station "
                    "if it still needs geocoding."
                )
            )
            return

        for candidate in candidates:
            self.stdout.write(
                f"\nCandidate {candidate.candidate_number}\n"
                f"  Name: {candidate.name}\n"
                f"  Address: {candidate.address}\n"
                f"  Latitude: {candidate.latitude}\n"
                f"  Longitude: {candidate.longitude}\n"
                f"  Types: {', '.join(candidate.types or [])}\n"
                f"  Google Place ID: {candidate.provider_place_id}"
            )

        self.stdout.write(
            "\nVerify the location before approving it.\n"
            "No coordinates have been changed.\n"
            "Approve with --approve N, using the candidate number."
        )

    @transaction.atomic
    def _approve(self, station_id, candidate_number):
        if candidate_number < 1:
            raise CommandError("--approve must be 1 or greater.")

        try:
            station = FuelStation.objects.select_for_update().get(
                pk=station_id
            )
        except FuelStation.DoesNotExist as exc:
            raise CommandError(
                f"Fuel station {station_id} was not found."
            ) from exc

        if (
            station.latitude is not None
            or station.longitude is not None
        ):
            raise CommandError(
                "This station already has coordinates. "
                "No changes were made."
            )

        try:
            candidate = StationGeocodeReview.objects.select_for_update().get(
                station=station,
                candidate_number=candidate_number,
                status=StationGeocodeReview.Status.PENDING,
            )
        except StationGeocodeReview.DoesNotExist as exc:
            raise CommandError(
                f"Pending candidate {candidate_number} was not found "
                f"for station #{station_id}. List the saved candidates "
                "and choose a pending candidate number."
            ) from exc

        now = timezone.now()

        station.latitude = candidate.latitude
        station.longitude = candidate.longitude
        station.geocode_status = "matched"
        station.save(
            update_fields=[
                "latitude",
                "longitude",
                "geocode_status",
                "updated_at",
            ]
        )

        candidate.status = StationGeocodeReview.Status.APPROVED
        candidate.reviewed_at = now
        candidate.save(update_fields=["status", "reviewed_at"])

        StationGeocodeReview.objects.filter(
            station=station,
            status=StationGeocodeReview.Status.PENDING,
        ).exclude(pk=candidate.pk).update(
            status=StationGeocodeReview.Status.REJECTED,
            reviewed_at=now,
        )

        # Invalidate cached station/planning data after approval.
        cache.set(
            "fuel-data-version",
            now.isoformat(),
            timeout=None,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Approved candidate {candidate_number} for "
                f"station #{station.pk}: {candidate.name} - "
                f"{candidate.address}\n"
                f"Coordinates: {candidate.latitude}, "
                f"{candidate.longitude}"
            )
        )
