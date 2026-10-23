
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP

from apps.fuel.services.exceptions import FuelCoverageError

MPG = 10.0
MAX_RANGE_MILES = 500.0
TANK_CAPACITY_GALLONS = MAX_RANGE_MILES / MPG
ARRIVAL_RESERVE_GALLONS = 2.0
MAX_PLANNED_LEG_MILES = (
    MAX_RANGE_MILES - ARRIVAL_RESERVE_GALLONS * MPG
)

MONEY = Decimal("0.01")
GALLON_PRECISION = Decimal("0.01")
EPSILON = 1e-6


@dataclass(frozen=True, slots=True)
class CandidateStation:
    station_id: int
    name: str
    address: str
    city: str
    state: str
    latitude: float
    longitude: float
    price_per_gallon: Decimal
    route_mile: float
    distance_from_route_miles: float
    location_precision: str = "matched"


@dataclass(frozen=True, slots=True)
class FuelStop:
    station: CandidateStation
    gallons_purchased: float
    estimated_cost: Decimal
    arrival_fuel_gallons: float
    departure_fuel_gallons: float


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _purchase_gallons(value: float) -> float:
    """Round fuel purchases upward to avoid understating fuel required."""
    return float(
        Decimal(str(max(0.0, value))).quantize(
            GALLON_PRECISION,
            rounding=ROUND_UP,
        )
    )


def _deduplicate_stations(
    stations: list[CandidateStation],
    route_distance_miles: float,
) -> list[CandidateStation]:
    ordered = sorted(
        (
            station
            for station in stations
            if 0 < station.route_mile < route_distance_miles
            and station.price_per_gallon > 0
        ),
        key=lambda station: station.route_mile,
    )

    distinct: list[CandidateStation] = []

    for station in ordered:
        if (
            distinct
            and station.route_mile - distinct[-1].route_mile < 0.5
        ):
            if station.price_per_gallon < distinct[-1].price_per_gallon:
                distinct[-1] = station
        else:
            distinct.append(station)

    return distinct


def _has_reachable_continuation(
    station: CandidateStation,
    stations: list[CandidateStation],
    route_distance_miles: float,
) -> bool:
    """Check that a refuelled vehicle can reach another station or destination."""
    remaining_distance = route_distance_miles - station.route_mile

    if remaining_distance <= MAX_PLANNED_LEG_MILES + EPSILON:
        return True

    return any(
        other.route_mile > station.route_mile + 0.01
        and other.route_mile - station.route_mile
        <= MAX_PLANNED_LEG_MILES + EPSILON
        for other in stations
    )


def optimize_fuel_plan(
    route_distance_miles: float,
    stations: list[CandidateStation],
    initial_fuel_gallons: float = TANK_CAPACITY_GALLONS,
) -> dict:
    """Plan feasible fuel stops using prices, range and a fuel reserve.

    Assumptions:
    - Fuel economy is 10 MPG.
    - Tank capacity and maximum range are 50 gallons and 500 miles.
    - The plan targets a 2-gallon reserve when reaching stops and destination.
    - Purchases are rounded upward to 0.01 gallon.
    - The price-aware greedy strategy is not guaranteed to find the
      globally cheapest possible plan.
    """
    if route_distance_miles < 0:
        raise ValueError("Route distance cannot be negative.")

    if not 0 <= initial_fuel_gallons <= TANK_CAPACITY_GALLONS:
        raise ValueError("Initial fuel must be between zero and tank capacity.")

    distinct = _deduplicate_stations(stations, route_distance_miles)

    fuel = initial_fuel_gallons
    current_mile = 0.0
    current_station: CandidateStation | None = None

    stops: list[FuelStop] = []
    total_purchase_cost = Decimal("0")

    while (
        route_distance_miles - current_mile
        > max(0.0, fuel - ARRIVAL_RESERVE_GALLONS) * MPG + EPSILON
    ):
        # Keep the safety reserve available when selecting the next stop.
        max_reachable_mile = min(
            current_mile
            + max(0.0, fuel - ARRIVAL_RESERVE_GALLONS) * MPG,
            current_mile + MAX_RANGE_MILES,
        )

        reachable = [
            station
            for station in distinct
            if current_mile + 0.01 < station.route_mile
            <= max_reachable_mile + EPSILON
            and _has_reachable_continuation(
                station,
                distinct,
                route_distance_miles,
            )
        ]

        if not reachable:
            raise FuelCoverageError(
                "No fuel station is reachable while preserving the "
                f"{ARRIVAL_RESERVE_GALLONS:.1f}-gallon reserve near "
                f"mile {current_mile:.1f}. Check station geocoding "
                "and route coverage."
            )

        # Prefer the cheapest reachable station that leaves a feasible onward
        # path. Break equal-price ties by choosing the earlier station.
        next_station = min(
            reachable,
            key=lambda station: (
                station.price_per_gallon,
                station.route_mile,
            ),
        )

        distance_to_station = next_station.route_mile - current_mile
        fuel_used = distance_to_station / MPG

        if fuel_used > fuel - ARRIVAL_RESERVE_GALLONS + EPSILON:
            raise FuelCoverageError(
                f"Insufficient fuel reserve to reach station at "
                f"mile {next_station.route_mile:.1f}."
            )

        fuel = max(0.0, fuel - fuel_used)
        current_mile = next_station.route_mile
        current_station = next_station

        remaining_distance = route_distance_miles - current_mile

        # Do not buy more fuel if the destination is reachable while
        # retaining the required reserve.
        if (
            remaining_distance
            <= max(0.0, fuel - ARRIVAL_RESERVE_GALLONS) * MPG + EPSILON
        ):
            break

        cheaper_stations = [
            station
            for station in distinct
            if station.route_mile > current_mile + 0.01
            and station.route_mile - current_mile
            <= MAX_PLANNED_LEG_MILES + EPSILON
            and station.price_per_gallon < current_station.price_per_gallon
            and _has_reachable_continuation(
                station,
                distinct,
                route_distance_miles,
            )
        ]

        if cheaper_stations:
            # Aim to reach the nearest cheaper station while retaining
            # the safety reserve.
            target_station = min(
                cheaper_stations,
                key=lambda station: station.route_mile,
            )
            target_distance = target_station.route_mile - current_mile
        else:
            # Otherwise, travel as far as possible without using the reserve.
            target_distance = min(
                MAX_PLANNED_LEG_MILES,
                remaining_distance,
            )

        target_fuel = (
            target_distance / MPG + ARRIVAL_RESERVE_GALLONS
        )
        gallons_needed = max(0.0, target_fuel - fuel)
        gallons_to_buy = _purchase_gallons(gallons_needed)

        available_capacity = TANK_CAPACITY_GALLONS - fuel

        if gallons_to_buy > available_capacity + EPSILON:
            # A capacity limit must never silently create an infeasible leg.
            gallons_to_buy = max(0.0, available_capacity)

        if gallons_to_buy + EPSILON < gallons_needed:
            raise FuelCoverageError(
                f"Tank capacity is insufficient to reach the next target "
                f"from mile {current_mile:.1f} while preserving the reserve."
            )

        if gallons_to_buy <= EPSILON:
            raise FuelCoverageError(
                f"Unable to purchase sufficient fuel at mile "
                f"{current_mile:.1f}."
            )

        purchase_decimal = Decimal(str(gallons_to_buy))
        cost = _money(
            current_station.price_per_gallon * purchase_decimal
        )

        arrival_fuel = fuel
        fuel = min(
            TANK_CAPACITY_GALLONS,
            fuel + gallons_to_buy,
        )
        total_purchase_cost += cost

        stops.append(
            FuelStop(
                station=current_station,
                gallons_purchased=gallons_to_buy,
                estimated_cost=cost,
                arrival_fuel_gallons=arrival_fuel,
                departure_fuel_gallons=fuel,
            )
        )

    # Validate that the final leg is feasible and preserves the reserve.
    final_leg = route_distance_miles - current_mile
    fuel_needed_for_final_leg = (
        final_leg / MPG + ARRIVAL_RESERVE_GALLONS
    )

    if fuel_needed_for_final_leg > fuel + EPSILON:
        raise FuelCoverageError(
            f"Insufficient fuel to reach the destination with the "
            f"{ARRIVAL_RESERVE_GALLONS:.1f}-gallon reserve. "
            f"Final leg: {final_leg:.1f} miles."
        )

    consumed_gallons = route_distance_miles / MPG

    valid_prices = [
        station.price_per_gallon for station in distinct
    ]
    average_route_price = (
        sum(valid_prices, Decimal("0")) / Decimal(len(valid_prices))
        if valid_prices
        else None
    )

    estimated_total_trip_cost = (
        _money(Decimal(str(consumed_gallons)) * average_route_price)
        if average_route_price is not None
        else None
    )

    estimated_initial_fuel_value = (
        _money(
            Decimal(str(initial_fuel_gallons)) * average_route_price
        )
        if average_route_price is not None
        else None
    )

    return {
        "route_distance_miles": round(route_distance_miles, 2),
        "estimated_fuel_consumed_gallons": round(consumed_gallons, 2),
        "fuel_purchased_gallons": round(
            sum(stop.gallons_purchased for stop in stops), 2
        ),
        "fuel_purchase_cost_usd": str(_money(total_purchase_cost)),
        "estimated_total_trip_fuel_cost_usd": (
            str(estimated_total_trip_cost)
            if estimated_total_trip_cost is not None
            else None
        ),
        "estimated_initial_fuel_value_usd": (
            str(estimated_initial_fuel_value)
            if estimated_initial_fuel_value is not None
            else None
        ),
        "fuel_price_estimation": {
            "method": "average price of geocoded candidate stations along the route",
            "average_price_per_gallon_usd": (
                str(_money(average_route_price))
                if average_route_price is not None
                else None
            ),
            "note": (
                "Total trip fuel cost estimates all fuel consumed, including "
                "fuel already in the tank at departure. Stop purchase cost "
                "reflects only purchases made at recommended stops."
            ),
        },
        "initial_fuel_gallons": round(initial_fuel_gallons, 2),
        "assumptions": {
            "mpg": MPG,
            "maximum_range_miles": MAX_RANGE_MILES,
            "tank_capacity_gallons": TANK_CAPACITY_GALLONS,
            "arrival_reserve_gallons": ARRIVAL_RESERVE_GALLONS,
            "initial_tank_cost_included_in_purchase_cost": False,
        },
        "stops": [
            {
                "station_id": stop.station.station_id,
                "name": stop.station.name,
                "address": stop.station.address,
                "city": stop.station.city,
                "state": stop.station.state,
                "latitude": stop.station.latitude,
                "longitude": stop.station.longitude,
                "route_mile": round(stop.station.route_mile, 2),
                "distance_from_route_miles": round(
                    stop.station.distance_from_route_miles, 2
                ),
                "location_precision": stop.station.location_precision,
                "price_per_gallon_usd": str(
                    stop.station.price_per_gallon
                ),
                "gallons_to_purchase": round(
                    stop.gallons_purchased, 2
                ),
                "estimated_cost_usd": str(stop.estimated_cost),
                "fuel_on_arrival_gallons": round(
                    stop.arrival_fuel_gallons, 2
                ),
                "fuel_on_departure_gallons": round(
                    stop.departure_fuel_gallons, 2
                ),
            }
            for stop in stops
        ],
    }
