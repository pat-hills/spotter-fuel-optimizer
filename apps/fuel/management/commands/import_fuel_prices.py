import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from uuid import uuid4
from django.db import transaction
from apps.fuel.models import FuelStation

class Command(BaseCommand):
    help = "Import the assessment fuel-price CSV into the local database."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["csv_path"])
        if not path.is_file():
            raise CommandError(f"CSV file does not exist: {path}")
        records = []
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            required = {"OPIS Truckstop ID", "Truckstop Name", "Address", "City", "State", "Rack ID", "Retail Price"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise CommandError("CSV is missing one or more expected assessment columns.")
            for line_number, row in enumerate(reader, start=2):
                try:
                    price = Decimal(row["Retail Price"])
                    if price <= 0:
                        continue
                    records.append(FuelStation(
                        source_id=f"{row['OPIS Truckstop ID']}:{row['Rack ID']}:{line_number}",
                        name=row["Truckstop Name"].strip(), address=row["Address"].strip(),
                        city=row["City"].strip(), state=row["State"].strip().upper()[:2],
                        rack_id=str(row["Rack ID"]).strip(), price_per_gallon=price,
                        geocode_status="pending",
                    ))
                except (InvalidOperation, TypeError, KeyError) as exc:
                    raise CommandError(f"Invalid price or missing field on CSV line {line_number}.") from exc
        FuelStation.objects.all().delete()
        FuelStation.objects.bulk_create(records, batch_size=1000)
        cache.set("fuel-data-version", uuid4().hex, timeout=None)
        self.stdout.write(self.style.SUCCESS(f"Imported {len(records)} fuel-price records. Coordinates remain pending geocoding."))
