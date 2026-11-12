from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.generated_catalog import (
    TARGET_TOTAL_LISTINGS as SYNTHETIC_TOTAL_LISTINGS,
    extend_seed_data as extend_synthetic_seed_data,
)
from app.inside_airbnb_catalog import (
    TARGET_TOTAL_LISTINGS,
    extend_seed_data as extend_inside_airbnb_seed_data,
)
from app.models import (
    Availability,
    Booking,
    Listing,
    ListingImage,
    Message,
    MessageThread,
    Review,
    TaskDefinition,
    User,
    WishlistItem,
)


DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
MIN_EXPECTED_LISTINGS = TARGET_TOTAL_LISTINGS
IMPORTED_AVAILABILITY_ANCHOR = date(2026, 5, 1)


def parse_date(value: str) -> date:
    return datetime.strptime(value, DATE_FORMAT).date()


def parse_datetime(value: str) -> datetime:
    return datetime.strptime(value, DATETIME_FORMAT)


def daterange(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current < end_date:
        yield current
        current += timedelta(days=1)


def load_seed_data(path: Path | None = None) -> dict:
    seed_path = path or settings.seed_file
    with seed_path.open("r", encoding="utf-8") as file:
        base_seed = json.load(file)
    synthetic_seed = extend_synthetic_seed_data(base_seed)
    return extend_inside_airbnb_seed_data(synthetic_seed)


def _generate_availability(
    listing: Listing,
    availability_start: date,
    availability_end: date,
    bookings: list[Booking],
) -> list[Availability]:
    blocked_dates = set()

    for blocked_range in listing.blocked_ranges:
        blocked_start = parse_date(blocked_range["start"])
        blocked_end = parse_date(blocked_range["end"])
        blocked_dates.update(daterange(blocked_start, blocked_end))

    for booking in bookings:
        if booking.status == "confirmed":
            blocked_dates.update(daterange(booking.check_in, booking.check_out))

    availability_entries = []
    for current_date in daterange(availability_start, availability_end):
        availability_entries.append(
            Availability(
                listing_id=listing.id,
                date=current_date,
                is_available=current_date not in blocked_dates,
            )
        )

    return availability_entries


def _generate_imported_availability(
    listing: Listing,
    bookings: list[Booking],
) -> list[Availability]:
    availability_by_date = {IMPORTED_AVAILABILITY_ANCHOR: True}

    for blocked_range in listing.blocked_ranges:
        for blocked_date in daterange(
            parse_date(blocked_range["start"]),
            parse_date(blocked_range["end"]),
        ):
            availability_by_date[blocked_date] = False

    for booking in bookings:
        if booking.status != "confirmed":
            continue
        for booked_date in daterange(booking.check_in, booking.check_out):
            availability_by_date[booked_date] = False

    return [
        Availability(
            listing_id=listing.id,
            date=availability_date,
            is_available=is_available,
        )
        for availability_date, is_available in sorted(availability_by_date.items())
    ]


def seed_database(session: Session, seed_data: dict) -> None:
    user_objects: dict[int, User] = {}
    listing_objects: dict[int, Listing] = {}
    booking_objects: list[Booking] = []

    for user_data in seed_data["users"]:
        user = User(**user_data)
        session.add(user)
        user_objects[user.id] = user

    session.flush()

    for listing_data in seed_data["listings"]:
        image_payloads = listing_data.pop("images", [])
        listing = Listing(**listing_data)
        session.add(listing)
        listing_objects[listing.id] = listing
        for image_payload in image_payloads:
            session.add(ListingImage(listing_id=listing.id, **image_payload))

    for review_data in seed_data["reviews"]:
        review = Review(
            **{
                **review_data,
                "created_at": parse_datetime(review_data["created_at"]),
            }
        )
        session.add(review)

    session.flush()

    for booking_data in seed_data["bookings"]:
        booking = Booking(
            **{
                **booking_data,
                "check_in": parse_date(booking_data["check_in"]),
                "check_out": parse_date(booking_data["check_out"]),
                "created_at": parse_datetime(booking_data["created_at"]),
            }
        )
        session.add(booking)
        booking_objects.append(booking)

    for wishlist_data in seed_data["wishlists"]:
        session.add(WishlistItem(**wishlist_data))

    for thread_data in seed_data["message_threads"]:
        messages = thread_data.pop("messages", [])
        thread = MessageThread(
            **{
                **thread_data,
                "last_message_at": parse_datetime(thread_data["last_message_at"]),
            }
        )
        session.add(thread)
        session.flush()
        for message_data in messages:
            session.add(
                Message(
                    thread_id=thread.id,
                    sender_id=message_data["sender_id"],
                    body=message_data["body"],
                    created_at=parse_datetime(message_data["created_at"]),
                )
            )

    for task_data in seed_data["tasks"]:
        session.add(TaskDefinition(**task_data))

    availability_start = parse_date(seed_data["availability_window"]["start"])
    availability_end = parse_date(seed_data["availability_window"]["end"])

    session.flush()

    bookings_by_listing: dict[int, list[Booking]] = {}
    for booking in booking_objects:
        bookings_by_listing.setdefault(booking.listing_id, []).append(booking)

    full_availability_listing_ids = {
        listing_id
        for listing_id in listing_objects
        if listing_id <= SYNTHETIC_TOTAL_LISTINGS
    }
    for listing_id in sorted(full_availability_listing_ids):
        listing = listing_objects[listing_id]
        session.add_all(
            _generate_availability(
                listing=listing,
                availability_start=availability_start,
                availability_end=availability_end,
                bookings=bookings_by_listing.get(listing.id, []),
            )
        )

    # Imported listings generate full date ranges lazily when a guest books.
    # Seed one early-May date so their browser date inputs do not fall back to
    # the host machine's current date and make benchmark stays unselectable.
    imported_listing_ids = set(listing_objects) - full_availability_listing_ids
    for listing_id in sorted(imported_listing_ids):
        listing = listing_objects[listing_id]
        session.add_all(
            _generate_imported_availability(
                listing=listing,
                bookings=bookings_by_listing.get(listing.id, []),
            )
        )


def _snapshot_paths() -> tuple[Path, Path] | None:
    if engine.url.get_backend_name() != "sqlite" or not engine.url.database:
        return None
    database = Path(engine.url.database)
    if str(database) == ":memory:":
        return None
    snapshot = Path(os.getenv("TRAVELMAP_SEED_SNAPSHOT", "/opt/webarena-seed/travelmap.sqlite3"))
    return database, snapshot


def create_seed_snapshot() -> None:
    """Bake the fully populated database once, after the image's seed import."""
    paths = _snapshot_paths()
    if paths is None:
        raise RuntimeError("Seed snapshots require a file-backed SQLite database")
    database, snapshot = paths
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    engine.dispose()
    temporary = snapshot.with_suffix(".tmp")
    with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(temporary)) as target:
        source.backup(target)
    temporary.replace(snapshot)


def restore_seed_snapshot() -> bool:
    paths = _snapshot_paths()
    if paths is None:
        return False
    database, snapshot = paths
    if not snapshot.is_file():
        return False
    database.parent.mkdir(parents=True, exist_ok=True)
    engine.dispose()
    # SQLite backup replaces the contents transactionally without unlinking a
    # database that an existing request connection may still have open.
    with closing(sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(database, timeout=60)) as target:
            source.backup(target)
    engine.dispose()
    return True


def reset_database() -> None:
    if restore_seed_snapshot():
        return
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_data = load_seed_data()
    with SessionLocal() as session:
        seed_database(session, seed_data)
        session.commit()


def ensure_database_seeded() -> None:
    Base.metadata.create_all(bind=engine)

    needs_catalog_refresh = False
    with SessionLocal() as session:
        has_users = session.scalar(select(User.id).limit(1))
        if has_users is None:
            seed_database(session, load_seed_data())
            session.commit()
            return

        listing_count = session.scalar(select(func.count(Listing.id))) or 0
        if listing_count < MIN_EXPECTED_LISTINGS:
            needs_catalog_refresh = True

    if needs_catalog_refresh:
        reset_database()
