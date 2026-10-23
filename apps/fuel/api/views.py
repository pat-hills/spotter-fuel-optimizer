
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fuel.api.serializers import FuelPlanRequestSerializer
from apps.fuel.services.geocoding import GoogleMapsGeocoder
from apps.fuel.services.planner import FuelPlanningService
from apps.fuel.services.routing import OsrmRoutingService


class FuelPlanAPIView(APIView):
    """Calculate a route and cost-aware refuelling plan."""

    def post(self, request):
        serializer = FuelPlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        service = FuelPlanningService(
            routing_service=OsrmRoutingService(),
            geocoder=GoogleMapsGeocoder(),
        )

        result = service.plan(
            serializer.validated_data["start"],
            serializer.validated_data["finish"],
        )

        return Response(result, status=status.HTTP_200_OK)
