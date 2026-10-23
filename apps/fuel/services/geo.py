
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MILES = 3958.7613
METERS_PER_MILE = 1609.344


@dataclass(frozen=True, slots=True)
class Coordinate:
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class RoutePoint:
    coordinate: Coordinate
    distance_miles: float


def haversine_miles(a: Coordinate, b: Coordinate) -> float:
    lat1, lat2 = radians(a.latitude), radians(b.latitude)
    delta_lat = lat2 - lat1
    delta_lon = radians(b.longitude - a.longitude)

    value = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )

    return 2 * EARTH_RADIUS_MILES * asin(min(1.0, sqrt(value)))


def project_to_route(
    station: Coordinate,
    route_points: list[RoutePoint],
) -> tuple[float, float]:
    """Project a station onto the nearest route segment in a local coordinate plane."""
    if not route_points:
        raise ValueError("Route geometry must contain at least one point.")

    if len(route_points) == 1:
        return (
            haversine_miles(station, route_points[0].coordinate),
            route_points[0].distance_miles,
        )

    miles_per_degree = 69.172
    latitude_scale = cos(radians(station.latitude))
    best_distance_squared = float("inf")
    best_route_mile = 0.0

    # Adjacent-pair iteration intentionally uses sequences of different lengths.
    for start, end in zip(route_points, route_points[1:]):  # noqa: B905
        ax = (
            (start.coordinate.longitude - station.longitude)
            * latitude_scale
            * miles_per_degree
        )
        ay = (start.coordinate.latitude - station.latitude) * miles_per_degree

        bx = (
            (end.coordinate.longitude - station.longitude)
            * latitude_scale
            * miles_per_degree
        )
        by = (end.coordinate.latitude - station.latitude) * miles_per_degree

        dx, dy = bx - ax, by - ay
        segment_length_squared = dx * dx + dy * dy

        if segment_length_squared == 0:
            fraction = 0.0
        else:
            fraction = max(
                0.0,
                min(
                    1.0,
                    -(ax * dx + ay * dy) / segment_length_squared,
                ),
            )

        projected_x = ax + fraction * dx
        projected_y = ay + fraction * dy
        distance_squared = projected_x**2 + projected_y**2

        if distance_squared < best_distance_squared:
            best_distance_squared = distance_squared
            best_route_mile = (
                start.distance_miles
                + fraction * (end.distance_miles - start.distance_miles)
            )

    return sqrt(best_distance_squared), best_route_mile


def build_route_points(
    coordinates: list[tuple[float, float]],
) -> list[RoutePoint]:
    points: list[RoutePoint] = []
    cumulative = 0.0
    previous = None

    for longitude, latitude in coordinates:
        current = Coordinate(latitude=latitude, longitude=longitude)

        if previous is not None:
            cumulative += haversine_miles(previous, current)

        points.append(RoutePoint(current, cumulative))
        previous = current

    return points
