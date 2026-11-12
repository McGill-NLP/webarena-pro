"""Flight search endpoint."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

from ..config import (
    BEST_FLIGHTS_COUNT,
    BEST_WEIGHT_DURATION,
    BEST_WEIGHT_PRICE,
    BEST_WEIGHT_STOPS,
    MAX_RESULTS,
    ROUND_TRIP_SAME_AIRLINE_DISCOUNT,
)
from ..data_loader import get_route_graph
from ..flight_generator import generate_flights_for_route
from ..hub_detector import compute_hub_scores
from ..models import FlightOffer, SearchRequest, SearchResponse, SortBy, TripType
from ..route_finder import find_routes
from ..seed_utils import make_seed
from ..eval_state import now_ms, record_search

router = APIRouter(prefix="/api", tags=["search"])

# Module-level hub cache
_hub_iatas: list[str] | None = None


def _get_hubs() -> list[str]:
    global _hub_iatas
    if _hub_iatas is None:
        graph = get_route_graph()
        _hub_iatas = compute_hub_scores(graph)
    return _hub_iatas


def _apply_filters(flights: list[FlightOffer], req: SearchRequest) -> list[FlightOffer]:
    f = req.filters
    result = flights

    if f.max_stops is not None:
        result = [fl for fl in result if fl.stops <= f.max_stops]

    if f.max_price is not None:
        result = [fl for fl in result if fl.price_usd <= f.max_price]

    if f.max_duration_minutes is not None:
        result = [fl for fl in result if fl.total_duration_minutes <= f.max_duration_minutes]

    if f.airlines:
        airline_set = set(f.airlines)
        result = [
            fl for fl in result
            if any(seg.airline_code in airline_set for seg in fl.segments)
        ]

    if f.departure_time_min:
        h, m = map(int, f.departure_time_min.split(":"))
        min_minutes = h * 60 + m
        result = [
            fl for fl in result
            if fl.departure.hour * 60 + fl.departure.minute >= min_minutes
        ]

    if f.departure_time_max:
        h, m = map(int, f.departure_time_max.split(":"))
        max_minutes = h * 60 + m
        result = [
            fl for fl in result
            if fl.departure.hour * 60 + fl.departure.minute <= max_minutes
        ]

    return result


def _sort_flights(flights: list[FlightOffer], sort_by: SortBy) -> list[FlightOffer]:
    if sort_by == SortBy.cheapest:
        return sorted(flights, key=lambda f: f.price_usd)
    elif sort_by == SortBy.fastest:
        return sorted(flights, key=lambda f: f.total_duration_minutes)
    else:  # best: balance of price and duration
        if not flights:
            return flights
        max_price = max(f.price_usd for f in flights) or 1
        max_dur = max(f.total_duration_minutes for f in flights) or 1
        return sorted(
            flights,
            key=lambda f: (f.price_usd / max_price) * 0.6 + (f.total_duration_minutes / max_dur) * 0.4,
        )


def _tag_best_flights(flights: list[FlightOffer], count: int = BEST_FLIGHTS_COUNT) -> None:
    """Tag top flights as is_best using a composite score.

    "Best" flights balance price, duration, and number of stops — like
    Google Flights' "Top departing flights" section.  The composite score
    normalizes each factor to [0,1] then weights them:
        score = W_price * (price/max_price)
              + W_duration * (duration/max_duration)
              + W_stops * (stops/max_stops)
    Lower score = better.  Top `count` flights are tagged is_best=True.
    """
    if len(flights) < 2:
        for f in flights:
            f.is_best = True
        return

    max_price = max(f.price_usd for f in flights) or 1
    max_dur = max(f.total_duration_minutes for f in flights) or 1
    max_stops = max(f.stops for f in flights) or 1

    scored = []
    for f in flights:
        score = (
            BEST_WEIGHT_PRICE * (f.price_usd / max_price)
            + BEST_WEIGHT_DURATION * (f.total_duration_minutes / max_dur)
            + BEST_WEIGHT_STOPS * (f.stops / max_stops)
        )
        scored.append((score, f))

    scored.sort(key=lambda x: x[0])
    for _, f in scored[:count]:
        f.is_best = True


@router.post("/search", response_model=SearchResponse)
async def search_flights(req: SearchRequest):
    started_at_ms = now_ms()
    graph = get_route_graph()
    hub_iatas = _get_hubs()

    if not req.legs:
        raise HTTPException(status_code=400, detail="At least one leg required")

    # Validate airports
    for leg in req.legs:
        if leg.origin.upper() not in graph.airports:
            raise HTTPException(status_code=404, detail=f"Airport {leg.origin} not found")
        if leg.destination.upper() not in graph.airports:
            raise HTTPException(status_code=404, detail=f"Airport {leg.destination} not found")

    # Validate booking window: flights can only be booked up to 12 months in advance
    from ..benchmark import today
    current_date = today()
    max_date = current_date + timedelta(days=365)
    for leg in req.legs:
        if leg.date < current_date:
            raise HTTPException(
                status_code=400,
                detail="Flights cannot be searched for dates that have already passed",
            )
        if leg.date > max_date:
            raise HTTPException(
                status_code=400,
                detail="Flights can only be booked up to 12 months in advance",
            )

    # Validate round-trip date order: return date must be >= departure date
    if req.trip_type == TripType.round_trip and len(req.legs) >= 2:
        if req.legs[1].date < req.legs[0].date:
            raise HTTPException(
                status_code=400,
                detail="Return date must be on or after the departure date",
            )

    # Validate multi-city date order: each leg date must be >= previous leg date
    if req.trip_type == TripType.multi_city and len(req.legs) >= 2:
        for i in range(1, len(req.legs)):
            if req.legs[i].date < req.legs[i - 1].date:
                raise HTTPException(
                    status_code=400,
                    detail=f"Flight {i + 1} date must be on or after flight {i} date",
                )

    # --- Multi-city: search each leg independently ---
    if req.trip_type == TripType.multi_city:
        multi_city_flights: list[list[FlightOffer]] = []
        max_stops = req.filters.max_stops

        for leg in req.legs:
            leg_origin = leg.origin.upper()
            leg_dest = leg.destination.upper()
            route_plans = find_routes(graph, leg_origin, leg_dest, hub_iatas, max_stops=max_stops)

            leg_flights: list[FlightOffer] = []
            for plan in route_plans:
                flights = generate_flights_for_route(
                    graph, plan, leg.date, req.cabin_class, hub_iatas
                )
                leg_flights.extend(flights)

            leg_flights = _apply_filters(leg_flights, req)
            leg_flights = _sort_flights(leg_flights, req.sort_by)
            leg_flights = leg_flights[:MAX_RESULTS]
            _tag_best_flights(leg_flights)
            multi_city_flights.append(leg_flights)

        first_leg = req.legs[0]
        origin = first_leg.origin.upper()
        destination = first_leg.destination.upper()
        search_id = str(make_seed(origin, destination, first_leg.date.isoformat()))

        response = SearchResponse(
            outbound_flights=[],
            return_flights=[],
            multi_city_flights=multi_city_flights,
            search_id=search_id,
            origin=origin,
            destination=destination,
            same_airline_discount=ROUND_TRIP_SAME_AIRLINE_DISCOUNT,
        )
        record_search(req, response, started_at_ms)
        return response

    # Generate outbound flights
    outbound_leg = req.legs[0]
    origin = outbound_leg.origin.upper()
    destination = outbound_leg.destination.upper()

    max_stops = req.filters.max_stops
    route_plans = find_routes(graph, origin, destination, hub_iatas, max_stops=max_stops)

    outbound_flights: list[FlightOffer] = []
    for plan in route_plans:
        flights = generate_flights_for_route(
            graph, plan, outbound_leg.date, req.cabin_class, hub_iatas
        )
        outbound_flights.extend(flights)

    outbound_flights = _apply_filters(outbound_flights, req)
    outbound_flights = _sort_flights(outbound_flights, req.sort_by)
    outbound_flights = outbound_flights[:MAX_RESULTS]
    _tag_best_flights(outbound_flights)

    # Generate return flights if round trip
    return_flights: list[FlightOffer] = []
    if req.trip_type.value == "round_trip" and len(req.legs) >= 2:
        return_leg = req.legs[1]
        ret_origin = return_leg.origin.upper()
        ret_dest = return_leg.destination.upper()
        ret_plans = find_routes(graph, ret_origin, ret_dest, hub_iatas, max_stops=max_stops)

        for plan in ret_plans:
            flights = generate_flights_for_route(
                graph, plan, return_leg.date, req.cabin_class, hub_iatas
            )
            return_flights.extend(flights)

        # Round-trip same-airline discount is now applied client-side based on
        # the user's selected outbound flight (not blanket across all outbound
        # airlines).  The discount rate is returned in same_airline_discount.

        return_flights = _apply_filters(return_flights, req)
        return_flights = _sort_flights(return_flights, req.sort_by)
        return_flights = return_flights[:MAX_RESULTS]
        _tag_best_flights(return_flights)

    search_id = str(make_seed(origin, destination, outbound_leg.date.isoformat()))

    response = SearchResponse(
        outbound_flights=outbound_flights,
        return_flights=return_flights,
        search_id=search_id,
        origin=origin,
        destination=destination,
        same_airline_discount=ROUND_TRIP_SAME_AIRLINE_DISCOUNT if return_flights else 1.0,
    )
    record_search(req, response, started_at_ms)
    return response
