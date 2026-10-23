from django.urls import path
from apps.fuel.api.views import FuelPlanAPIView

urlpatterns = [path("fuel-plans/optimize/", FuelPlanAPIView.as_view(), name="fuel-plan-optimize")]
