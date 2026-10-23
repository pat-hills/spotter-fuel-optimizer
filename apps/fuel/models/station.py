from django.core.validators import MinValueValidator
from django.db import models

class FuelStation(models.Model):
    source_id = models.CharField(max_length=80, db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500, blank=True)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.CharField(max_length=40, blank=True)
    price_per_gallon = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(0)])
    latitude = models.FloatField(null=True, blank=True, db_index=True)
    longitude = models.FloatField(null=True, blank=True, db_index=True)
    geocode_status = models.CharField(max_length=24, default="pending", db_index=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["state", "price_per_gallon"], name="fuel_state_price_idx"), models.Index(fields=["geocode_status", "state"], name="fuel_geocode_state_idx")]
        constraints = [models.CheckConstraint(condition=models.Q(price_per_gallon__gte=0), name="fuel_price_nonnegative")]
        ordering = ["price_per_gallon", "id"]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"



class StationGeocodeReview(models.Model):
    """Stores Google Places candidates for explicit human review."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    station = models.ForeignKey(
        FuelStation,
        on_delete=models.CASCADE,
        related_name="geocode_reviews",
    )
    provider = models.CharField(max_length=40, default="google_places")
    provider_place_id = models.CharField(max_length=255, blank=True)
    candidate_number = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=255, blank=True)
    address = models.CharField(max_length=500, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    types = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["station_id", "candidate_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["station", "candidate_number"],
                name="unique_station_geocode_candidate",
            ),
        ]

    def __str__(self):
        return f"{self.station_id}: {self.name} ({self.status})"
