"""Server-recorded search evidence and current bookings for deterministic grading.

The benchmark clock is frozen; execution filtering uses real request timestamps.
This journal is reset with the application and belongs to one worker container.
"""
from collections import deque
from copy import deepcopy
import os
import secrets
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/eval", tags=["evaluation"])
MAX_EVENTS = 4096
_events = deque()
_generation = uuid4().hex
_discarded_through_ms = None


def now_ms():
    return time.time_ns() // 1_000_000


def reset_evidence():
    global _generation, _discarded_through_ms
    _events.clear()
    _generation = uuid4().hex
    _discarded_through_ms = None


def _record(event):
    global _discarded_through_ms
    event = {"id": uuid4().hex, **event}
    if len(_events) >= MAX_EVENTS:
        removed = _events.popleft()
        _discarded_through_ms = max(_discarded_through_ms or 0, removed["started_at_ms"])
    _events.append(event)


def flight_evidence(flight):
    """No passenger/payment details or browser-supplied evaluation verdicts."""
    return {key: flight[key] for key in (
        "id", "origin", "destination", "departure", "total_duration_minutes", "stops",
    )}


def record_search(request, response, started_at_ms):
    data = response.model_dump(mode="json")
    # These are the actual filtered/capped offers returned by this search,
    # not all routes that happen to exist in the seed catalogue.
    offers = [*data["outbound_flights"], *data["return_flights"]]
    for leg in data["multi_city_flights"]:
        offers.extend(leg)
    _record({
        "kind": "search", "started_at_ms": started_at_ms,
        "trip_type": request.trip_type.value,
        "legs": [leg.model_dump(mode="json") for leg in request.legs],
        "offers": [flight_evidence(flight) for flight in offers],
    })


def record_booking(booking):
    _record({"kind": "booking", "started_at_ms": now_ms(),
             "booking_id": booking["booking_id"]})


@router.get("/state")
async def state(request: Request):
    expected = os.environ.get("WP_EVAL_TOKEN", "")
    if not expected:
        raise HTTPException(503, "Evaluation token is not configured")
    if not secrets.compare_digest(request.headers.get("X-Eval-Token", ""), expected):
        raise HTTPException(403, "Invalid evaluation token")
    from .booking_store import get_all_bookings

    bookings = [{
        "booking_id": item["booking_id"], "status": item["status"],
        "outbound_flight": flight_evidence(item["outbound_flight"]),
        "return_flight": flight_evidence(item["return_flight"]) if item.get("return_flight") else None,
        "multi_city_flights": [flight_evidence(flight) for flight in item.get("multi_city_flights", [])],
    } for item in get_all_bookings()]
    return {"schema_version": 1, "generation": _generation,
            "discarded_through_ms": _discarded_through_ms,
            "events": deepcopy(list(_events)), "bookings": bookings}
