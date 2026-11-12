"""Direct + 1-stop + 2-stop route discovery."""

from __future__ import annotations

from dataclasses import dataclass

from .config import (
    MAX_1STOP_DISTANCE_RATIO,
    MAX_2STOP_DISTANCE_RATIO,
    MIN_CONNECTION_MINUTES,
    MIN_LAYOVER_MINUTES,
)
from .data_loader import Route, RouteGraph


@dataclass
class RoutePlan:
    """A planned route from origin to destination (may have multiple legs)."""
    legs: list[Route]  # Each leg has origin implicitly from position
    waypoints: list[str]  # [origin, hub1, ..., destination]
    total_distance_km: int
    total_duration_min: int

    @property
    def stops(self) -> int:
        return len(self.legs) - 1


def _estimate_mct(graph: RouteGraph, arriving_origin: str, hub: str, departing_dest: str) -> int:
    """Estimate minimum connection time at *hub* based on domestic/international legs."""
    o = graph.airports.get(arriving_origin)
    h = graph.airports.get(hub)
    d = graph.airports.get(departing_dest)
    if not (o and h and d):
        return MIN_LAYOVER_MINUTES
    arr_type = "domestic" if o.country_code == h.country_code else "international"
    dep_type = "domestic" if h.country_code == d.country_code else "international"
    return MIN_CONNECTION_MINUTES.get((arr_type, dep_type), MIN_LAYOVER_MINUTES)


def find_routes(
    graph: RouteGraph,
    origin: str,
    destination: str,
    hub_iatas: list[str],
    max_stops: int | None = None,
) -> list[RoutePlan]:
    """Find all route plans from origin to destination.

    Returns direct, 1-stop, and 2-stop routes.
    """
    results: list[RoutePlan] = []

    if max_stops is not None and max_stops < 0:
        return results

    # Direct route
    direct = graph.get_direct_route(origin, destination)
    if direct:
        results.append(RoutePlan(
            legs=[direct],
            waypoints=[origin, destination],
            total_distance_km=direct.distance_km,
            total_duration_min=direct.duration_min,
        ))

    if max_stops is not None and max_stops == 0:
        return results

    # 1-stop routes through hubs
    direct_distance = direct.distance_km if direct else _estimate_distance(graph, origin, destination)
    if direct_distance is None:
        return results

    origin_routes = graph.get_outbound_routes(origin)

    for hub in hub_iatas:
        if hub == origin or hub == destination:
            continue

        leg1 = origin_routes.get(hub)
        if not leg1:
            continue

        leg2 = graph.get_direct_route(hub, destination)
        if not leg2:
            continue

        total_dist = leg1.distance_km + leg2.distance_km
        if total_dist > direct_distance * MAX_1STOP_DISTANCE_RATIO:
            continue

        mct = _estimate_mct(graph, origin, hub, destination)
        total_dur = leg1.duration_min + leg2.duration_min + mct
        results.append(RoutePlan(
            legs=[leg1, leg2],
            waypoints=[origin, hub, destination],
            total_distance_km=total_dist,
            total_duration_min=total_dur,
        ))

    if max_stops is not None and max_stops <= 1:
        return results

    # 2-stop routes through pairs of hubs (limit to top hubs for performance)
    top_hubs = hub_iatas[:60]
    for hub1 in top_hubs:
        if hub1 == origin or hub1 == destination:
            continue
        leg1 = origin_routes.get(hub1)
        if not leg1:
            continue

        hub1_routes = graph.get_outbound_routes(hub1)
        for hub2 in top_hubs:
            if hub2 == origin or hub2 == destination or hub2 == hub1:
                continue

            leg2 = hub1_routes.get(hub2)
            if not leg2:
                continue

            leg3 = graph.get_direct_route(hub2, destination)
            if not leg3:
                continue

            total_dist = leg1.distance_km + leg2.distance_km + leg3.distance_km
            if total_dist > direct_distance * MAX_2STOP_DISTANCE_RATIO:
                continue

            mct1 = _estimate_mct(graph, origin, hub1, hub2)
            mct2 = _estimate_mct(graph, hub1, hub2, destination)
            total_dur = (leg1.duration_min + leg2.duration_min + leg3.duration_min
                         + mct1 + mct2)
            results.append(RoutePlan(
                legs=[leg1, leg2, leg3],
                waypoints=[origin, hub1, hub2, destination],
                total_distance_km=total_dist,
                total_duration_min=total_dur,
            ))

    return results


def _estimate_distance(graph: RouteGraph, origin: str, destination: str) -> int | None:
    """Estimate great-circle distance between two airports using coordinates."""
    import math

    o = graph.airports.get(origin)
    d = graph.airports.get(destination)
    if not o or not d:
        return None

    lat1, lon1 = math.radians(o.latitude), math.radians(o.longitude)
    lat2, lon2 = math.radians(d.latitude), math.radians(d.longitude)

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return int(c * 6371)  # Earth radius in km
