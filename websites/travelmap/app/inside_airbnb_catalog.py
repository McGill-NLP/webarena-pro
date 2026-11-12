from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import random
from typing import Any


SOURCE_SAMPLE_SIZE = 10_000
TARGET_TOTAL_LISTINGS = 10_300
CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "inside_airbnb_sample.json"
SEEDED_RESERVATION_GUEST_ID = 1_000_000
SEEDED_RESERVATION_PREFIX = "PRE-"
SEEDED_RESERVATION_RANDOM_SEED = 20260718
SEEDED_RESERVATION_WINDOWS = (
    (date(2026, 6, 8), date(2026, 7, 3), 5, 10),
    (date(2026, 7, 27), date(2026, 9, 1), 5, 10),
    (date(2026, 9, 1), date(2027, 3, 31), 2, 7),
)
SEEDED_RESERVATIONS_PER_IMPORTED_LISTING = len(SEEDED_RESERVATION_WINDOWS)
SEEDED_RATING_RANDOM_SEED = 20260718
SEEDED_RATING_CENTER = 4.05
SEEDED_RATING_SOURCE_MIDPOINT = 4.5
SEEDED_RATING_SOURCE_SCALE = 1.35
SEEDED_RATING_JITTER_STDDEV = 0.45

# Keep every benchmark-critical stay open while still distributing imported
# reservations across the rest of the calendar.
PROTECTED_STAY_RANGES = (
    (date(2026, 5, 3), date(2026, 5, 12)),
    (date(2026, 5, 20), date(2026, 5, 24)),
    (date(2026, 6, 5), date(2026, 6, 8)),
    (date(2026, 7, 3), date(2026, 7, 20)),
    (date(2026, 7, 23), date(2026, 7, 27)),
    (date(2026, 10, 30), date(2026, 11, 11)),
)


def _overlaps_protected_range(check_in: date, check_out: date) -> bool:
    return any(
        check_out > protected_start and check_in < protected_end
        for protected_start, protected_end in PROTECTED_STAY_RANGES
    )


def _seeded_reservations(listing: dict[str, Any]) -> list[dict[str, Any]]:
    rng = random.Random(f"{SEEDED_RESERVATION_RANDOM_SEED}:{listing['id']}")
    reservations = []

    for reservation_index, (
        window_start,
        window_end,
        minimum_nights,
        maximum_nights,
    ) in enumerate(SEEDED_RESERVATION_WINDOWS, start=1):
        for _ in range(1_000):
            nights = rng.randint(minimum_nights, maximum_nights)
            latest_start = window_end - timedelta(days=nights)
            horizon_days = (latest_start - window_start).days
            check_in = window_start + timedelta(days=rng.randint(0, horizon_days))
            check_out = check_in + timedelta(days=nights)
            if not _overlaps_protected_range(check_in, check_out):
                break
        else:
            raise RuntimeError(
                f"Could not place seeded reservation {reservation_index} "
                f"for listing {listing['id']}"
            )

        created_date = check_in - timedelta(days=rng.randint(30, 120))
        created_at = datetime.combine(created_date, time(hour=rng.randint(8, 20)))
        total_price = round(
            nights * float(listing["price_per_night"])
            + float(listing.get("cleaning_fee", 0))
            + float(listing.get("service_fee", 0)),
            2,
        )
        reservations.append(
            {
                "id": (
                    1_000_000
                    + int(listing["id"]) * SEEDED_RESERVATIONS_PER_IMPORTED_LISTING
                    + reservation_index
                ),
                "confirmation_code": (
                    f"{SEEDED_RESERVATION_PREFIX}{int(listing['id']):05d}-{reservation_index}"
                ),
                "listing_id": int(listing["id"]),
                "guest_id": SEEDED_RESERVATION_GUEST_ID,
                "check_in": check_in.isoformat(),
                "check_out": check_out.isoformat(),
                "guests": rng.randint(1, min(4, int(listing["max_guests"]))),
                "total_price": total_price,
                "status": "confirmed",
                "created_at": created_at.isoformat(timespec="seconds"),
            }
        )

    return reservations


def _broadened_rating(listing: dict[str, Any]) -> float:
    """Preserve source-rating signal while avoiding an unrealistic 4.8-star cluster."""
    rng = random.Random(f"{SEEDED_RATING_RANDOM_SEED}:rating:{listing['id']}")
    source_rating = float(listing["rating"])
    broadened_rating = (
        SEEDED_RATING_CENTER
        + SEEDED_RATING_SOURCE_SCALE
        * (source_rating - SEEDED_RATING_SOURCE_MIDPOINT)
        + rng.gauss(0, SEEDED_RATING_JITTER_STDDEV)
    )
    return round(max(1.0, min(broadened_rating, 5.0)), 2)


def extend_seed_data(seed_data: dict[str, Any]) -> dict[str, Any]:
    """Add the checked-in Inside Airbnb sample to the task-critical base seed."""
    starting_listing_count = len(seed_data.get("listings", []))
    if starting_listing_count >= TARGET_TOTAL_LISTINGS:
        return seed_data

    with CATALOG_PATH.open("r", encoding="utf-8") as sample_file:
        sample = json.load(sample_file)

    if len(sample.get("listings", [])) != SOURCE_SAMPLE_SIZE:
        raise ValueError(
            f"Inside Airbnb sample has {len(sample.get('listings', [])):,} listings; "
            f"expected exactly {SOURCE_SAMPLE_SIZE:,}."
        )

    additions_needed = TARGET_TOTAL_LISTINGS - starting_listing_count
    listings = sample["listings"][:additions_needed]
    if len(listings) != additions_needed:
        raise ValueError(
            f"Inside Airbnb sample has {len(listings):,} usable listings; "
            f"{additions_needed:,} are required to reach {TARGET_TOTAL_LISTINGS:,}."
        )

    required_host_ids = {listing["host_id"] for listing in listings}
    hosts = [host for host in sample["hosts"] if host["id"] in required_host_ids]

    expanded = deepcopy(seed_data)
    existing_user_ids = {user["id"] for user in expanded["users"]}
    existing_user_emails = {user["email"] for user in expanded["users"]}
    expanded["users"].extend(
        deepcopy(host)
        for host in hosts
        if host["id"] not in existing_user_ids and host["email"] not in existing_user_emails
    )
    seeded_guest_email = "seeded-reservations@travelmap.invalid"
    if (
        SEEDED_RESERVATION_GUEST_ID not in existing_user_ids
        and seeded_guest_email not in existing_user_emails
    ):
        expanded["users"].append(
            {
                "id": SEEDED_RESERVATION_GUEST_ID,
                "name": "Seeded Reservation Guest",
                "email": seeded_guest_email,
                "password": "seeded-reservations-disabled",
                "is_host": False,
                "hometown": "",
                "bio": "System-owned guest used for deterministic imported-listing reservations.",
                "avatar_url": "",
            }
        )
    imported_listings = deepcopy(listings)
    for listing in imported_listings:
        listing["rating"] = _broadened_rating(listing)
    expanded["listings"].extend(imported_listings)
    expanded["bookings"].extend(
        reservation
        for listing in imported_listings
        for reservation in _seeded_reservations(listing)
    )
    return expanded
