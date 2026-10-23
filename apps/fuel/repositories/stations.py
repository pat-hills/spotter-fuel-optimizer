from django.db.models import QuerySet
from apps.fuel.models import FuelStation

def stations_near_bounds(min_lat: float, max_lat: float, min_lon: float, max_lon: float, limit: int) -> QuerySet[FuelStation]:
    return FuelStation.objects.filter(
        geocode_status__in=["matched", "approximate"], latitude__isnull=False, longitude__isnull=False,
        latitude__gte=min_lat, latitude__lte=max_lat,
        longitude__gte=min_lon, longitude__lte=max_lon,
    ).order_by("id")[:limit]
