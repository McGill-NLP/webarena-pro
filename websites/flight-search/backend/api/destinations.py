"""Popular destinations and cheap flights endpoints."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Query

from ..data_loader import get_route_graph
from ..price_engine import compute_calendar_price
from ..seed_utils import seeded_random

router = APIRouter(prefix="/api/destinations", tags=["destinations"])


def _cheapest_in_window(origin: str, dest: str, distance_km: int, num_carriers: int, dest_continent: str) -> tuple[float, str]:
    """Find the cheapest economy price across the next 90 days.

    Returns (cheapest_price, cheapest_date_iso).
    """
    from ..benchmark import today as _today
    today = _today()
    best_price = float("inf")
    best_date = today + timedelta(days=14)

    for day_offset in range(1, 91):
        target = today + timedelta(days=day_offset)
        rng = seeded_random("indicative", origin, dest, target.isoformat())
        price = compute_calendar_price(
            distance_km=distance_km,
            cabin_class="economy",
            target_date=target,
            num_carriers=num_carriers,
            dest_continent=dest_continent,
            rng=rng,
        )
        if price < best_price:
            best_price = price
            best_date = target

    return best_price, best_date.isoformat()


@router.get("/popular")
async def popular_destinations(
    origin: str = Query(..., min_length=3, max_length=3),
    limit: int = Query(8, ge=1, le=20),
):
    """Return top destinations from an origin, ranked by destination hub_score."""
    graph = get_route_graph()
    if origin.upper() not in graph.airports:
        return {"destinations": []}

    origin_upper = origin.upper()
    routes = graph.get_outbound_routes(origin_upper)
    origin_airport = graph.airports[origin_upper]

    scored = []
    for dest_iata, route in routes.items():
        dest_airport = graph.airports.get(dest_iata)
        if not dest_airport:
            continue
        price, cheapest_date = _cheapest_in_window(
            origin_upper, dest_iata, route.distance_km,
            len(route.carriers), dest_airport.continent,
        )
        scored.append({
            "iata": dest_iata,
            "city": dest_airport.city_name,
            "country": dest_airport.country,
            "country_code": dest_airport.country_code,
            "price_usd": round(price),
            "cheapest_date": cheapest_date,
            "hub_score": dest_airport.hub_score,
            "distance_km": route.distance_km,
            "is_domestic": dest_airport.country_code == origin_airport.country_code,
        })

    # Sort by hub_score descending (most popular destinations first)
    scored.sort(key=lambda x: -x["hub_score"])
    return {"origin": origin_upper, "destinations": scored[:limit]}


@router.get("/cheap-flights")
async def cheap_flights(
    origin: str = Query(..., min_length=3, max_length=3),
    category: str = Query("popular", pattern="^(domestic|international|popular)$"),
    limit: int = Query(8, ge=1, le=20),
):
    """Return cheapest flights from an origin, filtered by category."""
    graph = get_route_graph()
    if origin.upper() not in graph.airports:
        return {"flights": []}

    origin_upper = origin.upper()
    routes = graph.get_outbound_routes(origin_upper)
    origin_airport = graph.airports[origin_upper]

    items = []
    for dest_iata, route in routes.items():
        dest_airport = graph.airports.get(dest_iata)
        if not dest_airport:
            continue

        is_domestic = dest_airport.country_code == origin_airport.country_code

        if category == "domestic" and not is_domestic:
            continue
        if category == "international" and is_domestic:
            continue

        price, cheapest_date = _cheapest_in_window(
            origin_upper, dest_iata, route.distance_km,
            len(route.carriers), dest_airport.continent,
        )
        items.append({
            "iata": dest_iata,
            "city": dest_airport.city_name,
            "country": dest_airport.country,
            "country_code": dest_airport.country_code,
            "price_usd": round(price),
            "cheapest_date": cheapest_date,
            "distance_km": route.distance_km,
            "is_domestic": is_domestic,
        })

    # Sort by price ascending (cheapest first)
    items.sort(key=lambda x: x["price_usd"])
    return {"origin": origin_upper, "category": category, "flights": items[:limit]}
