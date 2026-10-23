from apps.fuel.services.geo import Coordinate, build_route_points, haversine_miles, project_to_route


def test_haversine_distance_is_positive():
    assert haversine_miles(Coordinate(40.0, -83.0), Coordinate(41.0, -83.0)) > 60


def test_project_station_to_route_returns_distance_and_progress():
    points = build_route_points([(-83.0, 40.0), (-82.0, 40.0)])
    distance, progress = project_to_route(Coordinate(40.01, -82.5), points)
    assert distance < 2
    assert 20 < progress < 30
