"""Generate concrete flights for a route + date."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from zoneinfo import ZoneInfo

from .config import (
    AIRCRAFT_BY_DISTANCE,
    CONNECTING_BASE_DISCOUNT,
    CURFEW_FACTORS,
    DEPARTURE_WEIGHT_JITTER,
    DEPARTURE_WEIGHTS,
    EMISSIONS_KG_PER_KM,
    HUB_FLIGHT_BONUS,
    LEGROOM_RANGES,
    MAX_FLIGHTS_MULTI_CARRIER,
    MAX_FLIGHTS_SINGLE_CARRIER,
    MAX_LAYOVER_MINUTES,
    MIN_CONNECTION_MINUTES,
    MIN_FLIGHTS_PER_DAY,
    MIN_LAYOVER_MINUTES,
    OVERNIGHT_EXEMPT_ROUTES,
    POPULARITY_LATEST_EXTENSION_MAX,
    POPULARITY_TIME_LIMITS,
    POWER_AIRCRAFT,
    PREMIUM_CLASS_AMENITY_BOOST,
    SAME_AIRLINE_CONNECTION_DISCOUNT,
    SHORT_CONNECTION_MINUTES,
    VIDEO_AIRCRAFT,
    WIFI_AIRCRAFT,
)
from .data_loader import Route, RouteGraph
from .models import CabinClass, FlightOffer, FlightSegment, LayoverInfo
from .price_engine import compute_price
from .route_finder import RoutePlan
from .seed_utils import seeded_random


def _pick_aircraft(distance_km: int, rng: random.Random) -> str:
    for max_dist, aircraft_list in AIRCRAFT_BY_DISTANCE:
        if distance_km <= max_dist:
            return rng.choice(aircraft_list)
    return "777-300ER"


def _make_flight_number(carrier_iata: str, rng: random.Random) -> str:
    return f"{carrier_iata}{rng.randint(100, 9999)}"


def _generate_amenities(
    aircraft: str, cabin_class: CabinClass, distance_km: int, rng: random.Random,
) -> dict:
    """Generate seat amenities based on aircraft, cabin class, and distance."""
    cls = cabin_class.value
    lo, hi = LEGROOM_RANGES.get(cls, (29, 32))
    legroom = rng.randint(lo, hi)

    is_premium = cls in ("business", "first")
    boost = PREMIUM_CLASS_AMENITY_BOOST if is_premium else 0.0

    # WiFi
    wifi_prob = min(1.0, WIFI_AIRCRAFT.get(aircraft, 0.3) + boost)
    has_wifi = rng.random() < wifi_prob
    wifi_type = None
    if has_wifi:
        # Free WiFi more common on premium classes and newer aircraft
        free_prob = 0.7 if is_premium else (0.3 if aircraft.startswith(("787", "A35")) else 0.12)
        wifi_type = "Free Wi-Fi" if rng.random() < free_prob else "Wi-Fi for a fee"

    # Power & USB
    power_prob = min(1.0, POWER_AIRCRAFT.get(aircraft, 0.2) + boost)
    has_power = rng.random() < power_prob
    # USB slightly more common than AC power
    has_usb = has_power or rng.random() < min(1.0, power_prob + 0.15)

    # Video/IFE
    video_prob = min(1.0, VIDEO_AIRCRAFT.get(aircraft, 0.05) + boost)
    # Long-haul (>4000km) gets a boost
    if distance_km > 4000:
        video_prob = min(1.0, video_prob + 0.15)
    has_video = rng.random() < video_prob
    video_type = None
    if has_video:
        if aircraft in ("A380", "777-300ER", "787-9", "787-10", "A350-900", "A350-1000"):
            video_type = "On-demand video"
        elif distance_km > 3000:
            video_type = "On-demand video" if rng.random() < 0.7 else "Seatback screen"
        else:
            video_type = "Live TV" if rng.random() < 0.4 else "Seatback screen"

    return {
        "legroom_inches": legroom,
        "has_wifi": has_wifi,
        "wifi_type": wifi_type,
        "has_power": has_power,
        "has_usb": has_usb,
        "has_video": has_video,
        "video_type": video_type,
    }


def _classify_route_type(origin_continent: str, dest_continent: str) -> str:
    """Classify a route for departure time distribution selection.

    Returns a key into DEPARTURE_WEIGHTS.
    """
    if origin_continent == dest_continent:
        return "domestic"
    o, d = origin_continent, dest_continent
    if o == "NA" and d == "EU":
        return "na_to_eu"
    if o == "EU" and d == "NA":
        return "eu_to_na"
    if o == "NA" and d == "AS":
        return "na_to_asia"
    if o == "AS" and d == "NA":
        return "asia_to_na"
    if o == "EU" and d == "AS":
        return "eu_to_asia"
    if o == "AS" and d == "EU":
        return "asia_to_eu"
    return "default"


def _build_departure_weights(
    route_type: str,
    num_carriers: int,
    origin_route_count: int,
    rng: random.Random,
) -> list[float]:
    """Build hourly departure weights adjusted for popularity, curfew, and jitter.

    Returns a 24-element list of non-negative floats (one weight per hour 0–23).

    Overnight-exempt routes (e.g. asia_to_eu with 23:00–02:30 departures)
    skip the popularity window and curfew so their late-night pattern is
    preserved intact.
    """
    base = list(DEPARTURE_WEIGHTS.get(route_type, DEPARTURE_WEIGHTS["default"]))
    weights = [float(w) for w in base]

    is_overnight = route_type in OVERNIGHT_EXEMPT_ROUTES

    if not is_overnight:
        # 1. Popularity-based time window: zero out hours outside the range
        earliest, latest = 7, 21  # defaults
        for min_carriers, eh, lh in POPULARITY_TIME_LIMITS:
            if num_carriers >= min_carriers:
                earliest, latest = eh, lh
                break
        # Random extension up to 1.5 h on the latest hour
        if num_carriers >= 2:
            latest = min(23, latest + rng.randint(0, POPULARITY_LATEST_EXTENSION_MAX) // 60)
        for h in range(0, earliest):
            weights[h] = 0.0
        for h in range(latest + 1, 24):
            weights[h] = 0.0

        # 2. Airport curfew: reduce midnight–5 AM based on airport size
        curfew_factor = 0.01
        for min_routes, factor in CURFEW_FACTORS:
            if origin_route_count >= min_routes:
                curfew_factor = factor
                break
        for h in range(0, 6):
            weights[h] *= curfew_factor

    # 3. Per-route jitter: ±DEPARTURE_WEIGHT_JITTER on each hour
    for h in range(24):
        if weights[h] > 0:
            jitter = 1.0 - DEPARTURE_WEIGHT_JITTER + 2 * DEPARTURE_WEIGHT_JITTER * rng.random()
            weights[h] *= jitter

    return weights


def _sample_departure_minutes(
    weights: list[float], num_flights: int, rng: random.Random,
) -> list[int]:
    """Sample N departure times (minutes since midnight) from hourly weights.

    Each sampled departure gets a random minute offset within its chosen hour.
    Returns sorted list.
    """
    total = sum(weights)
    if total <= 0:
        # Fallback: uniform 7 AM – 9 PM
        return sorted(rng.randint(7 * 60, 21 * 60) for _ in range(num_flights))

    # Sample hours via weighted random selection
    hours = rng.choices(range(24), weights=weights, k=num_flights)
    # Convert to minutes with random offset within the hour
    minutes = [h * 60 + rng.randint(0, 59) for h in hours]
    return sorted(minutes)


def _carrier_weights_at_airport(
    graph: RouteGraph, origin: str, leg_carriers: list[dict],
) -> list[float]:
    """Weight carriers by their presence at the origin airport.

    Carriers that operate more routes from this airport (hub carriers)
    get higher selection weight, so they appear on more flights.
    """
    # Count how many routes each carrier operates from origin
    carrier_route_counts: dict[str, int] = {}
    for route in graph.airports[origin].routes:
        for carrier in route.carriers:
            iata = carrier["iata"]
            carrier_route_counts[iata] = carrier_route_counts.get(iata, 0) + 1

    weights = []
    for carrier in leg_carriers:
        count = carrier_route_counts.get(carrier["iata"], 1)
        # Square-root scaling: hubs get more weight but don't completely dominate
        weights.append(count ** 0.5)
    return weights


def _get_timezone(graph: RouteGraph, iata: str) -> ZoneInfo:
    airport = graph.airports.get(iata)
    if airport and airport.timezone:
        try:
            return ZoneInfo(airport.timezone)
        except KeyError:
            pass
    return ZoneInfo("UTC")


def _leg_type(graph: RouteGraph, origin_iata: str, dest_iata: str) -> str:
    """Return 'domestic' if both airports are in the same country, else 'international'."""
    o = graph.airports.get(origin_iata)
    d = graph.airports.get(dest_iata)
    if o and d and o.country_code == d.country_code:
        return "domestic"
    return "international"


def _min_connection_minutes(
    graph: RouteGraph,
    arriving_origin: str,
    hub: str,
    departing_dest: str,
) -> int:
    """Return the minimum connection time at *hub* given the arriving and departing legs."""
    arr_type = _leg_type(graph, arriving_origin, hub)
    dep_type = _leg_type(graph, hub, departing_dest)
    return MIN_CONNECTION_MINUTES.get((arr_type, dep_type), MIN_LAYOVER_MINUTES)


def generate_flights_for_route(
    graph: RouteGraph,
    route_plan: RoutePlan,
    departure_date: date,
    cabin_class: CabinClass,
    hub_iatas: list[str],
) -> list[FlightOffer]:
    """Generate concrete flight offers for a route plan on a given date."""
    origin = route_plan.waypoints[0]
    destination = route_plan.waypoints[-1]

    # Seed based on route + date for determinism
    seed_key = f"{origin}-{destination}-{departure_date.isoformat()}-{cabin_class.value}"
    rng = seeded_random(seed_key, *route_plan.waypoints)

    if route_plan.stops == 0:
        return _generate_direct_flights(graph, route_plan, departure_date, cabin_class, rng)
    else:
        return _generate_connecting_flights(graph, route_plan, departure_date, cabin_class, rng)


def _generate_direct_flights(
    graph: RouteGraph,
    route_plan: RoutePlan,
    departure_date: date,
    cabin_class: CabinClass,
    rng: random.Random,
) -> list[FlightOffer]:
    """Generate multiple direct flight options for a single-leg route."""
    leg = route_plan.legs[0]
    origin = route_plan.waypoints[0]
    destination = route_plan.waypoints[1]

    origin_airport = graph.airports[origin]
    dest_airport = graph.airports[destination]
    origin_route_count = len(origin_airport.routes)

    # Number of flights based on carrier count
    num_carriers = len(leg.carriers)
    if num_carriers == 1:
        num_flights = rng.randint(MIN_FLIGHTS_PER_DAY, MAX_FLIGHTS_SINGLE_CARRIER)
    elif num_carriers <= 3:
        num_flights = rng.randint(3, 8)
    else:
        num_flights = rng.randint(8, MAX_FLIGHTS_MULTI_CARRIER)

    # Hub airport bonus: major airports generate more flights
    for min_routes, bonus_min, bonus_max in HUB_FLIGHT_BONUS:
        if origin_route_count >= min_routes:
            num_flights += rng.randint(bonus_min, bonus_max)
            break

    # Realistic departure time distribution based on route type
    route_type = _classify_route_type(origin_airport.continent, dest_airport.continent)
    dep_weights = _build_departure_weights(route_type, num_carriers, origin_route_count, rng)
    departure_hours = _sample_departure_minutes(dep_weights, num_flights, rng)

    origin_tz = _get_timezone(graph, origin)
    dest_tz = _get_timezone(graph, destination)

    # Pre-compute carrier weights for hub-airline bias
    carrier_wts = _carrier_weights_at_airport(graph, origin, leg.carriers)

    flights = []
    for dep_minutes in departure_hours:
        carrier = rng.choices(leg.carriers, weights=carrier_wts, k=1)[0]
        dep_hour = dep_minutes // 60
        dep_min = dep_minutes % 60

        departure_dt = datetime(
            departure_date.year, departure_date.month, departure_date.day,
            dep_hour, dep_min,
            tzinfo=origin_tz,
        )

        # Calculate arrival
        arrival_dt = departure_dt + timedelta(minutes=leg.duration_min)
        arrival_dt = arrival_dt.astimezone(dest_tz)

        price = compute_price(
            distance_km=leg.distance_km,
            cabin_class=cabin_class.value,
            departure_date=departure_date,
            departure_hour=dep_hour,
            num_carriers=num_carriers,
            dest_continent=dest_airport.continent,
            rng=rng,
        )

        flight_id = f"{origin}{destination}{departure_date.isoformat()}{dep_minutes}{carrier['iata']}"

        aircraft = _pick_aircraft(leg.distance_km, rng)
        amenities = _generate_amenities(aircraft, cabin_class, leg.distance_km, rng)

        # Overnight: compare local calendar dates in their respective timezones.
        # Python .date() on a tz-aware datetime returns the local date in that tz.
        is_overnight = arrival_dt.date() != departure_dt.date()

        segment = FlightSegment(
            airline_code=carrier["iata"],
            airline_name=carrier["name"],
            flight_number=_make_flight_number(carrier["iata"], rng),
            aircraft=aircraft,
            origin=origin,
            origin_city=origin_airport.city_name,
            destination=destination,
            destination_city=dest_airport.city_name,
            departure=departure_dt,
            arrival=arrival_dt,
            duration_minutes=leg.duration_min,
            is_overnight=is_overnight,
            **amenities,
        )

        emissions = int(leg.distance_km * EMISSIONS_KG_PER_KM.get(cabin_class.value, 0.09))

        flights.append(FlightOffer(
            id=flight_id,
            segments=[segment],
            total_duration_minutes=leg.duration_min,
            stops=0,
            price_usd=price,
            cabin_class=cabin_class,
            origin=origin,
            destination=destination,
            departure=departure_dt,
            arrival=arrival_dt,
            emissions_kg=emissions,
        ))

    return flights


def _generate_connecting_flights(
    graph: RouteGraph,
    route_plan: RoutePlan,
    departure_date: date,
    cabin_class: CabinClass,
    rng: random.Random,
) -> list[FlightOffer]:
    """Generate connecting flight options (1-stop or 2-stop)."""
    origin = route_plan.waypoints[0]
    destination = route_plan.waypoints[-1]
    origin_airport = graph.airports[origin]
    dest_airport = graph.airports[destination]
    origin_route_count = len(origin_airport.routes)

    # Realistic departure times for the first leg
    first_leg = route_plan.legs[0]
    num_first_carriers = len(first_leg.carriers) if first_leg.carriers else 1
    route_type = _classify_route_type(origin_airport.continent, dest_airport.continent)
    dep_weights = _build_departure_weights(route_type, num_first_carriers, origin_route_count, rng)

    # Generate 2-5 options per connecting route
    num_options = rng.randint(2, 5)
    dep_times = _sample_departure_minutes(dep_weights, num_options, rng)

    flights = []
    for option_idx in range(num_options):
        departure_minutes = dep_times[option_idx]

        segments = []
        layover_infos: list[LayoverInfo] = []
        current_time = datetime(
            departure_date.year, departure_date.month, departure_date.day,
            departure_minutes // 60, departure_minutes % 60,
            tzinfo=_get_timezone(graph, origin),
        )
        total_price = 0.0
        total_duration = 0

        valid = True
        for i, leg in enumerate(route_plan.legs):
            leg_origin = route_plan.waypoints[i]
            leg_dest = route_plan.waypoints[i + 1]
            origin_tz = _get_timezone(graph, leg_origin)
            dest_tz = _get_timezone(graph, leg_dest)
            origin_ap = graph.airports[leg_origin]
            dest_ap = graph.airports[leg_dest]

            if not leg.carriers:
                valid = False
                break
            leg_cwts = _carrier_weights_at_airport(graph, leg_origin, leg.carriers)
            carrier = rng.choices(leg.carriers, weights=leg_cwts, k=1)[0]
            departure_dt = current_time.astimezone(origin_tz)
            arrival_dt = departure_dt + timedelta(minutes=leg.duration_min)
            arrival_dt = arrival_dt.astimezone(dest_tz)

            # Overnight: compare local calendar dates in their respective timezones
            is_overnight = arrival_dt.date() != departure_dt.date()

            # Per-leg price with connection discount
            # (see price_engine.py and config.py for full pricing docs)
            leg_price = compute_price(
                distance_km=leg.distance_km,
                cabin_class=cabin_class.value,
                departure_date=departure_date,
                departure_hour=departure_dt.hour,
                num_carriers=len(leg.carriers),
                dest_continent=dest_ap.continent,
                rng=rng,
                is_connection=True,
            )
            leg_price *= CONNECTING_BASE_DISCOUNT
            total_price += leg_price

            aircraft = _pick_aircraft(leg.distance_km, rng)
            amenities = _generate_amenities(aircraft, cabin_class, leg.distance_km, rng)

            segments.append(FlightSegment(
                airline_code=carrier["iata"],
                airline_name=carrier["name"],
                flight_number=_make_flight_number(carrier["iata"], rng),
                aircraft=aircraft,
                origin=leg_origin,
                origin_city=origin_ap.city_name,
                destination=leg_dest,
                destination_city=dest_ap.city_name,
                departure=departure_dt,
                arrival=arrival_dt,
                duration_minutes=leg.duration_min,
                is_overnight=is_overnight,
                **amenities,
            ))

            # Add layover time for next leg
            if i < len(route_plan.legs) - 1:
                next_dest = route_plan.waypoints[i + 2]
                min_conn = _min_connection_minutes(graph, leg_origin, leg_dest, next_dest)
                layover = rng.randint(min_conn, MAX_LAYOVER_MINUTES)
                current_time = arrival_dt + timedelta(minutes=layover)
                total_duration += leg.duration_min + layover

                # Layover overnight: both times at the hub airport (same tz).
                # arrival_dt is already in dest_tz (= hub tz).
                # current_time inherits that tz after timedelta addition.
                layover_overnight = current_time.date() != arrival_dt.date()

                layover_infos.append(LayoverInfo(
                    duration_minutes=layover,
                    airport=leg_dest,
                    airport_city=dest_ap.city_name,
                    is_overnight=layover_overnight,
                    is_short_connection=layover < SHORT_CONNECTION_MINUTES,
                ))

                # Check if layover pushes to next day too far
                if (current_time - datetime(
                    departure_date.year, departure_date.month, departure_date.day,
                    tzinfo=origin_tz
                )).days > 1:
                    valid = False
                    break
            else:
                total_duration += leg.duration_min

        if not valid:
            continue

        # Same-airline connection discount: if all segments are on the same
        # carrier, apply an additional discount (bundled itinerary fare).
        carrier_codes = {seg.airline_code for seg in segments}
        if len(carrier_codes) == 1:
            total_price *= SAME_AIRLINE_CONNECTION_DISCOUNT

        total_price = round(total_price, 0)
        first_departure = segments[0].departure
        last_arrival = segments[-1].arrival

        flight_id = (
            f"{origin}{destination}{departure_date.isoformat()}"
            f"{departure_minutes}{'-'.join(route_plan.waypoints)}{option_idx}"
        )

        total_distance = sum(leg.distance_km for leg in route_plan.legs)
        emissions = int(total_distance * EMISSIONS_KG_PER_KM.get(cabin_class.value, 0.09))

        flights.append(FlightOffer(
            id=flight_id,
            segments=segments,
            layovers=layover_infos,
            total_duration_minutes=total_duration,
            stops=route_plan.stops,
            price_usd=total_price,
            cabin_class=cabin_class,
            origin=origin,
            destination=destination,
            departure=first_departure,
            arrival=last_arrival,
            emissions_kg=emissions,
        ))

    return flights
