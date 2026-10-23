
from decimal import Decimal

import pytest

from apps.fuel.services.exceptions import FuelCoverageError
from apps.fuel.services.optimizer import (
    CandidateStation,
    optimize_fuel_plan,
)


def station(station_id, mile, price):
    return CandidateStation(
        station_id=station_id,
        name=f"Station {station_id}",
        address="Test highway",
        city="Test City",
        state="TX",
        latitude=30.0,
        longitude=-97.0,
        price_per_gallon=Decimal(str(price)),
        route_mile=float(mile),
        distance_from_route_miles=0.5,
    )


def test_short_route_needs_no_stops_when_starting_full():
    result = optimize_fuel_plan(300, [])

    assert result["stops"] == []
    assert result["estimated_fuel_consumed_gallons"] == 30
    assert result["fuel_purchase_cost_usd"] == "0.00"


def test_long_route_has_feasible_legs_and_tank_levels():
    result = optimize_fuel_plan(
        795.12,
        [
            station(1, 169.03, "3.299"),
            station(2, 633.37, "3.007333"),
        ],
    )

    stops = result["stops"]
    assert stops

    previous_mile = 0.0
    previous_fuel = result["initial_fuel_gallons"]

    for stop in stops:
        leg_distance = stop["route_mile"] - previous_mile
        fuel_needed = leg_distance / 10.0

        assert leg_distance <= 500.0
        assert fuel_needed <= previous_fuel + 1e-6
        assert stop["fuel_on_arrival_gallons"] >= 0
        assert stop["fuel_on_departure_gallons"] <= 50.0
        assert stop["fuel_on_departure_gallons"] >= (
            stop["fuel_on_arrival_gallons"]
        )

        previous_mile = stop["route_mile"]
        previous_fuel = stop["fuel_on_departure_gallons"]

    final_leg = result["route_distance_miles"] - previous_mile
    assert final_leg <= previous_fuel * 10.0 + 1e-6


def test_purchase_rounding_never_understates_required_fuel():
    result = optimize_fuel_plan(
        795.12,
        [
            station(1, 169.03, "3.299"),
            station(2, 633.37, "3.007333"),
        ],
    )

    final_stop = result["stops"][-1]
    remaining_distance = (
        result["route_distance_miles"] - final_stop["route_mile"]
    )
    displayed_departure_fuel = final_stop["fuel_on_departure_gallons"]

    assert displayed_departure_fuel * 10.0 >= remaining_distance


def test_fails_when_no_station_can_be_reached():
    with pytest.raises(FuelCoverageError):
        optimize_fuel_plan(900, [station(1, 600, "3.50")])


def test_cheapest_reachable_station_is_selected_at_start():
    result = optimize_fuel_plan(
        700,
        [
            station(1, 100, "3.80"),
            station(2, 200, "3.10"),
            station(3, 300, "3.40"),
        ],
    )

    assert result["stops"]
    assert result["stops"][0]["station_id"] == 2


def test_purchase_costs_are_currency_rounded():
    result = optimize_fuel_plan(
        650,
        [
            station(1, 400, "3.3333"),
            station(2, 600, "3.10"),
        ],
    )

    assert all(
        len(stop["estimated_cost_usd"].split(".")[-1]) == 2
        for stop in result["stops"]
    )


def test_rejects_invalid_initial_fuel():
    with pytest.raises(ValueError):
        optimize_fuel_plan(100, [], initial_fuel_gallons=51)
