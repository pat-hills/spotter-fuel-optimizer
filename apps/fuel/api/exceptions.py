from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from apps.fuel.services.exceptions import FuelCoverageError, GeocodingError, RoutingProviderError


def api_exception_handler(exc, context):
    if isinstance(exc, FuelCoverageError):
        return Response({"error": {"code": "fuel_coverage_insufficient", "message": str(exc)}}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    if isinstance(exc, GeocodingError):
        return Response({"error": {"code": "location_not_resolved", "message": str(exc)}}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    if isinstance(exc, RoutingProviderError):
        return Response({"error": {"code": "routing_unavailable", "message": str(exc)}}, status=status.HTTP_502_BAD_GATEWAY)
    response = exception_handler(exc, context)
    if response is not None:
        response.data = {"error": {"code": "request_error", "details": response.data}}
    return response
