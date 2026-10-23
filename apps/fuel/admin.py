from django.contrib import admin
from apps.fuel.models import FuelStation

@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "price_per_gallon", "geocode_status")
    list_filter = ("state", "geocode_status")
    search_fields = ("name", "city", "address")
    list_select_related = False
