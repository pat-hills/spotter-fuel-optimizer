
import csv
import io
from uuid import uuid4

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.fuel.models import FuelStation


class Command(BaseCommand):
    help = "Geocode fuel stations using the US Census batch geocoder."
    endpoint = (
        "https://geocoding.geo.census.gov/"
        "geocoder/locations/addressbatch"
    )
    batch_limit = 10000

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of pending stations to process.",
        )

    def _batch_geocode(self, stations):
        upload = io.StringIO()
        writer = csv.writer(upload, lineterminator="\n")
        submitted_ids = set()

        for station in stations:
            street = (station.address or "").strip()
            if not street:
                continue

            writer.writerow([
                station.pk,
                street,
                (station.city or "").strip(),
                (station.state or "").strip(),
                "",
            ])
            submitted_ids.add(station.pk)

        if not submitted_ids:
            return {}

        payload = upload.getvalue()
        if len(payload.encode("utf-8")) > 5 * 1024 * 1024:
            raise CommandError(
                "The geocoding batch exceeds the 5 MB service limit."
            )

        user_agent = getattr(settings, "GEOCODING_USER_AGENT", "")
        if (
            not user_agent
            or "your-email@example.com" in user_agent
        ):
            raise CommandError(
                "Set GEOCODING_USER_AGENT in .env to include "
                "a real contact email before geocoding."
            )

        try:
            response = requests.post(
                self.endpoint,
                data={"benchmark": "Public_AR_Current"},
                files={
                    "addressFile": (
                        "fuel-stations.csv",
                        payload,
                        "text/csv",
                    )
                },
                headers={"User-Agent": user_agent},
                timeout=(10, 120),
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(
                "Census geocoding failed. No station records were changed."
            ) from exc

        results = {}

        for row in csv.reader(io.StringIO(response.text)):
            if len(row) < 6:
                continue

            try:
                station_id = int(row[0].strip())
            except (ValueError, IndexError):
                continue

            if station_id not in submitted_ids:
                continue

            match_status = row[2].strip()
            coordinate_text = row[5].strip()

            if match_status == "Match" and coordinate_text:
                try:
                    longitude, latitude = (
                        float(value.strip())
                        for value in coordinate_text.split(",")
                    )
                except (ValueError, TypeError):
                    results[station_id] = (None, None, "unmatched")
                    continue

                if (
                    -180 <= longitude <= 180
                    and -90 <= latitude <= 90
                ):
                    results[station_id] = (
                        latitude,
                        longitude,
                        "matched",
                    )
                else:
                    results[station_id] = (None, None, "unmatched")

            elif match_status == "Tie":
                results[station_id] = (None, None, "ambiguous")
            else:
                results[station_id] = (None, None, "unmatched")

        return results

    def handle(self, *args, **options):
        limit = options["limit"]

        if limit is not None and limit < 1:
            raise CommandError("--limit must be greater than zero.")

        queryset = FuelStation.objects.filter(
            geocode_status="pending"
        ).order_by("id")

        if limit is not None:
            queryset = queryset[:limit]

        stations = list(queryset)

        if not stations:
            self.stdout.write("No stations require geocoding.")
            return

        if len(stations) > self.batch_limit:
            raise CommandError(
                "The Census service supports at most 10,000 "
                "records per batch."
            )

        results = self._batch_geocode(stations)
        now = timezone.now()

        for station in stations:
            latitude, longitude, status = results.get(
                station.pk,
                (None, None, "unmatched"),
            )
            station.latitude = latitude
            station.longitude = longitude
            station.geocode_status = status
            station.updated_at = now

        with transaction.atomic():
            FuelStation.objects.bulk_update(
                stations,
                [
                    "latitude",
                    "longitude",
                    "geocode_status",
                    "updated_at",
                ],
                batch_size=1000,
            )

        cache.set("fuel-data-version", uuid4().hex, timeout=None)

        counts = {}
        for station in stations:
            counts[station.geocode_status] = (
                counts.get(station.geocode_status, 0) + 1
            )

        summary = ", ".join(
            f"{count} {status}"
            for status, count in sorted(counts.items())
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {len(stations)} stations: {summary}"
            )
        )
