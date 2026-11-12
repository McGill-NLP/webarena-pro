"""Calendar pricing endpoint — cheapest price per day for a month."""

from __future__ import annotations

import calendar
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..data_loader import get_route_graph
from ..models import CalendarDay, CalendarResponse, CabinClass
from ..price_engine import compute_calendar_price
from ..seed_utils import seeded_random

router = APIRouter(prefix="/api", tags=["calendar"])


@router.get("/calendar", response_model=CalendarResponse)
async def get_calendar(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    year: int = Query(..., ge=2025, le=2028),
    month: int = Query(..., ge=1, le=12),
    cabin_class: CabinClass = Query(CabinClass.economy),
):
    graph = get_route_graph()
    origin = origin.upper()
    destination = destination.upper()

    if origin not in graph.airports:
        raise HTTPException(status_code=404, detail=f"Airport {origin} not found")
    if destination not in graph.airports:
        raise HTTPException(status_code=404, detail=f"Airport {destination} not found")

    route = graph.get_direct_route(origin, destination)
    if not route:
        # Try to estimate distance for pricing
        from ..route_finder import _estimate_distance
        distance = _estimate_distance(graph, origin, destination)
        if distance is None:
            raise HTTPException(status_code=404, detail="No route found")
        num_carriers = 2  # default estimate
    else:
        distance = route.distance_km
        num_carriers = len(route.carriers)

    dest_airport = graph.airports[destination]
    num_days = calendar.monthrange(year, month)[1]

    days = []
    for day in range(1, num_days + 1):
        d = date(year, month, day)
        rng = seeded_random(origin, destination, d.isoformat(), "calendar")
        price = compute_calendar_price(
            distance_km=distance,
            cabin_class=cabin_class.value,
            target_date=d,
            num_carriers=num_carriers,
            dest_continent=dest_airport.continent,
            rng=rng,
        )
        days.append(CalendarDay(date=d, cheapest_price=price))

    return CalendarResponse(
        origin=origin,
        destination=destination,
        year=year,
        month=month,
        days=days,
    )
