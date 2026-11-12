"""Airport autocomplete and info endpoints."""

from fastapi import APIRouter, HTTPException, Query

from ..data_loader import get_route_graph
from ..models import AirportInfo, AutocompleteResult

router = APIRouter(prefix="/api/airports", tags=["airports"])


@router.get("/autocomplete", response_model=list[AutocompleteResult])
async def autocomplete(q: str = Query(..., min_length=1, max_length=50)):
    graph = get_route_graph()
    airports = graph.search_airports(q, limit=10)
    return [
        AutocompleteResult(
            iata=a.iata,
            name=a.name,
            city_name=a.city_name,
            country=a.country,
            display_name=a.display_name,
            hub_score=a.hub_score,
        )
        for a in airports
    ]


@router.get("/{iata}", response_model=AirportInfo)
async def get_airport(iata: str):
    graph = get_route_graph()
    iata = iata.upper()
    airport = graph.airports.get(iata)
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {iata} not found")
    return AirportInfo(
        iata=airport.iata,
        name=airport.name,
        city_name=airport.city_name,
        country=airport.country,
        country_code=airport.country_code,
        continent=airport.continent,
        latitude=airport.latitude,
        longitude=airport.longitude,
        timezone=airport.timezone,
        hub_score=airport.hub_score,
        route_count=len(airport.routes),
    )
