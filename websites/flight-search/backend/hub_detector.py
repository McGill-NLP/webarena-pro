"""Compute hub scores for airports.

Hub score = route_count * carrier_diversity * continent_reach
Used for: connecting flight search (top hubs as waypoints) and autocomplete ranking.
"""

from __future__ import annotations

from .config import HUB_MIN_ROUTES, HUB_TOP_N
from .data_loader import RouteGraph


def compute_hub_scores(graph: RouteGraph) -> list[str]:
    """Compute hub scores for all airports. Returns top hub IATA codes.

    Modifies airports in-place to set hub_score.
    """
    for airport in graph.airports.values():
        route_count = len(airport.routes)
        if route_count < 5:
            airport.hub_score = 0.0
            continue

        # Carrier diversity: unique carriers across all routes
        carriers = set()
        for route in airport.routes:
            for c in route.carriers:
                carriers.add(c["iata"])
        carrier_diversity = len(carriers)

        # Continent reach: unique continents reachable
        continents = set()
        for route in airport.routes:
            dest = graph.airports.get(route.destination)
            if dest:
                continents.add(dest.continent)
        continent_reach = len(continents)

        airport.hub_score = route_count * (carrier_diversity ** 0.5) * (continent_reach ** 0.3)

    # Normalize scores to 0-100
    max_score = max((a.hub_score for a in graph.airports.values()), default=1.0)
    if max_score > 0:
        for airport in graph.airports.values():
            airport.hub_score = round(airport.hub_score / max_score * 100, 2)

    # Return top hubs
    hubs = sorted(
        [a for a in graph.airports.values() if len(a.routes) >= HUB_MIN_ROUTES],
        key=lambda a: -a.hub_score,
    )
    return [h.iata for h in hubs[:HUB_TOP_N]]
