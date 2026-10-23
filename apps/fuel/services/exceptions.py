class RoutingProviderError(Exception):
    """Raised when a routing provider cannot return a usable route."""

class GeocodingError(Exception):
    """Raised when a location cannot be resolved to coordinates."""

class FuelCoverageError(Exception):
    """Raised when available stations cannot support a feasible fuel plan."""
