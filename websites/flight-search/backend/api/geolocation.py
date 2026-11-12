"""Geolocation endpoint — resolves client IP to location + nearest airports."""

from __future__ import annotations

import ipaddress
import math

import httpx
from fastapi import APIRouter, Request

from ..config import COUNTRY_CURRENCY_MAP
from ..data_loader import get_route_graph

router = APIRouter(prefix="/api/geolocation", tags=["geolocation"])

# Fallback for truly unresolvable cases
_FALLBACK = {
    "country_code": "US",
    "city": "New York",
    "lat": 40.7128,
    "lon": -74.0060,
    "currency": "USD",
}


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/loopback/reserved."""
    try:
        return ipaddress.ip_address(ip_str).is_private
    except ValueError:
        return True


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _nearest_airports(lat: float, lon: float, limit: int = 3) -> list[dict]:
    """Find nearest airports by haversine distance."""
    graph = get_route_graph()
    scored = []
    for airport in graph.airports.values():
        if airport.latitude == 0.0 and airport.longitude == 0.0:
            continue
        dist = _haversine_km(lat, lon, airport.latitude, airport.longitude)
        scored.append((dist, airport))
    scored.sort(key=lambda x: x[0])
    return [
        {
            "iata": a.iata,
            "name": a.display_name,
            "city": a.city_name,
            "distance_km": round(d),
        }
        for d, a in scored[:limit]
    ]


async def _resolve_ip(client_ip: str) -> str:
    """If client_ip is private (localhost, LAN), discover the public IP."""
    if not _is_private_ip(client_ip):
        return client_ip
    # Ask ip-api.com without an IP — it returns the server's public IP info
    # Or use a lightweight service to get the public IP first
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("https://api.ipify.org?format=json")
            data = resp.json()
            return data.get("ip", client_ip)
    except Exception:
        return client_ip


@router.get("")
async def geolocate(request: Request):
    """Resolve client IP to location, currency, and nearest airports."""
    # Get real client IP (behind proxy headers)
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else "127.0.0.1"

    # If IP is private (localhost/LAN), resolve to public IP
    lookup_ip = await _resolve_ip(client_ip)

    # Try ip-api.com (free, no key, 45 req/min)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"http://ip-api.com/json/{lookup_ip}?fields=status,country,countryCode,city,lat,lon")
            data = resp.json()
            if data.get("status") == "success":
                country_code = data.get("countryCode", "US")
                lat = data.get("lat", _FALLBACK["lat"])
                lon = data.get("lon", _FALLBACK["lon"])
                city = data.get("city", _FALLBACK["city"])
                currency = COUNTRY_CURRENCY_MAP.get(country_code, "USD")
                return {
                    "country_code": country_code,
                    "city": city,
                    "lat": lat,
                    "lon": lon,
                    "currency": currency,
                    "nearest_airports": _nearest_airports(lat, lon),
                }
    except Exception:
        pass

    # Fallback
    return {
        **_FALLBACK,
        "nearest_airports": _nearest_airports(_FALLBACK["lat"], _FALLBACK["lon"]),
    }
