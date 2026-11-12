"""Load airline_routes.json and build in-memory route graph + search index."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class Route:
    destination: str
    distance_km: int
    duration_min: int
    carriers: list[dict]  # [{"iata": "AA", "name": "American Airlines"}, ...]


@dataclass
class Airport:
    iata: str
    name: str
    city_name: str
    country: str
    country_code: str
    continent: str
    latitude: float
    longitude: float
    timezone: str
    elevation: int
    icao: str
    display_name: str
    routes: list[Route] = field(default_factory=list)
    hub_score: float = 0.0


class RouteGraph:
    """In-memory route graph and search index."""

    def __init__(self) -> None:
        self.airports: dict[str, Airport] = {}
        # route_map[origin_iata][dest_iata] = Route
        self.route_map: dict[str, dict[str, Route]] = {}
        # Search index: lowercase tokens → set of IATA codes
        self._search_index: dict[str, set[str]] = {}

    def load(self, filepath: str) -> None:
        with open(filepath) as f:
            data: dict = json.load(f)

        for iata, info in data.items():
            routes = []
            for r in info.get("routes", []):
                if not r["carriers"]:
                    continue  # Skip routes with no carrier data
                routes.append(Route(
                    destination=r["iata"],
                    distance_km=r["km"],
                    duration_min=r["min"],
                    carriers=r["carriers"],
                ))

            airport = Airport(
                iata=iata,
                name=info["name"],
                city_name=info["city_name"],
                country=info["country"],
                country_code=info["country_code"],
                continent=info["continent"],
                latitude=float(info["latitude"]) if info.get("latitude") is not None else 0.0,
                longitude=float(info["longitude"]) if info.get("longitude") is not None else 0.0,
                timezone=info.get("timezone", "UTC"),
                elevation=info.get("elevation", 0),
                icao=info.get("icao", ""),
                display_name=info.get("display_name", f"{info['city_name']} ({iata})"),
                routes=routes,
            )
            self.airports[iata] = airport

            # Build route map
            self.route_map.setdefault(iata, {})
            for route in routes:
                self.route_map[iata][route.destination] = route

            # Build search index
            self._index_airport(airport)

    def _index_airport(self, airport: Airport) -> None:
        tokens = set()
        # IATA code
        tokens.add(airport.iata.lower())
        # City name tokens
        for word in airport.city_name.lower().split():
            tokens.add(word)
        # Airport name tokens
        for word in airport.name.lower().split():
            tokens.add(word)
        # Country
        for word in airport.country.lower().split():
            tokens.add(word)
        # Country code
        tokens.add(airport.country_code.lower())

        for token in tokens:
            # Index exact token and all prefixes ≥ 2 chars
            for i in range(2, len(token) + 1):
                prefix = token[:i]
                self._search_index.setdefault(prefix, set()).add(airport.iata)

    def search_airports(self, query: str, limit: int = 10) -> list[Airport]:
        """Search airports by IATA code, city, name, or country."""
        q = query.strip().lower()
        if not q:
            return []

        # Exact IATA match first
        if len(q) == 3 and q.upper() in self.airports:
            exact = self.airports[q.upper()]
            results = [exact]
            # Add more results from prefix search
            candidates = self._search_index.get(q, set())
            for iata in candidates:
                if iata != exact.iata:
                    results.append(self.airports[iata])
                if len(results) >= limit:
                    break
            return results[:limit]

        # Split query into tokens, intersect matches
        query_tokens = q.split()
        if not query_tokens:
            return []

        # Get candidates matching first token
        candidates = self._search_index.get(query_tokens[0], set()).copy()

        # Intersect with additional tokens
        for token in query_tokens[1:]:
            token_matches = self._search_index.get(token, set())
            candidates &= token_matches

        if not candidates:
            return []

        # Sort by hub score (descending), then alphabetically
        airports = [self.airports[iata] for iata in candidates if iata in self.airports]
        airports.sort(key=lambda a: (-a.hub_score, a.city_name))
        return airports[:limit]

    def get_direct_route(self, origin: str, destination: str) -> Route | None:
        return self.route_map.get(origin, {}).get(destination)

    def get_outbound_routes(self, origin: str) -> dict[str, Route]:
        return self.route_map.get(origin, {})


# Singleton
_graph: RouteGraph | None = None


def get_route_graph() -> RouteGraph:
    global _graph
    if _graph is None:
        _graph = RouteGraph()
        data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "airline_routes.json")
        _graph.load(data_path)
    return _graph
