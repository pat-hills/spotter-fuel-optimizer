from django.core.validators import MinValueValidator
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="FuelStation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_id", models.CharField(db_index=True, max_length=80)),
                ("name", models.CharField(max_length=255)),
                ("address", models.CharField(blank=True, max_length=500)),
                ("city", models.CharField(max_length=120)),
                ("state", models.CharField(db_index=True, max_length=2)),
                ("rack_id", models.CharField(blank=True, max_length=40)),
                ("price_per_gallon", models.DecimalField(decimal_places=6, max_digits=9, validators=[MinValueValidator(0)])),
                ("latitude", models.FloatField(blank=True, db_index=True, null=True)),
                ("longitude", models.FloatField(blank=True, db_index=True, null=True)),
                ("geocode_status", models.CharField(db_index=True, default="pending", max_length=24)),
                ("source_updated_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["price_per_gallon", "id"]},
        ),
        migrations.AddIndex(model_name="fuelstation", index=models.Index(fields=["state", "price_per_gallon"], name="fuel_state_price_idx")),
        migrations.AddIndex(model_name="fuelstation", index=models.Index(fields=["geocode_status", "state"], name="fuel_geocode_state_idx")),
        migrations.AddConstraint(model_name="fuelstation", constraint=models.CheckConstraint(condition=models.Q(("price_per_gallon__gte", 0)), name="fuel_price_nonnegative")),
    ]
