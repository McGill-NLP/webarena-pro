import unittest
from datetime import date, datetime
import json
from pathlib import Path
import statistics

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
from starlette.requests import Request

from app.database import SessionLocal
from app.main import (
    app,
    _parse_optional_float,
    _parse_optional_int,
    block_listing_dates,
    book_listing,
    cancel_booking,
    home,
    host_dashboard,
    listing_detail,
    merge_ranges,
    send_listing_message,
    toggle_wishlist,
)
from app.content import get_listing_property_category
from app.models import Availability, Booking, Listing, Review, TaskDefinition
from app.seed import reset_database
from app.inside_airbnb_catalog import (
    PROTECTED_STAY_RANGES,
    SEEDED_RESERVATION_GUEST_ID,
    SEEDED_RESERVATION_PREFIX,
    SEEDED_RESERVATIONS_PER_IMPORTED_LISTING,
)
from app.tasks import evaluate_task


class WebArenaAirbnbTests(unittest.TestCase):
    def setUp(self):
        reset_database()

    def _build_request(self, path: str, user_id: int | None = None, method: str = "GET") -> Request:
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "session": {"user_id": user_id} if user_id is not None else {},
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "http_version": "1.1",
            "app": app,
        }
        return Request(scope)

    def test_seeded_task_catalog_exists(self):
        with SessionLocal() as db:
            tasks = db.scalars(
                select(TaskDefinition).options(joinedload(TaskDefinition.persona)).order_by(TaskDefinition.id)
            ).all()
            self.assertEqual(len(tasks), 10)
            self.assertEqual(tasks[0].persona.email, "avery@example.com")

    def test_catalog_contains_original_synthetic_and_ten_thousand_source_stays(self):
        with SessionLocal() as db:
            listings = db.scalars(select(Listing)).all()
            self.assertEqual(len(listings), 10_300)

            original_slugs = set(
                db.scalars(select(Listing.slug).where(Listing.id <= 300)).all()
            )

        seed_path = Path(__file__).resolve().parents[1] / "data" / "seed_data.json"
        base_seed = json.loads(seed_path.read_text(encoding="utf-8"))
        from app.generated_catalog import extend_seed_data as extend_synthetic_seed_data

        expected_seed = extend_synthetic_seed_data(base_seed)
        self.assertEqual(len(original_slugs), 300)
        self.assertEqual(original_slugs, {listing["slug"] for listing in expected_seed["listings"]})
        self.assertEqual(len(expected_seed["reviews"]), 595)
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count(Review.id))), 595)

    def test_inside_airbnb_listing_has_a_source_image(self):
        with SessionLocal() as db:
            listing = db.scalar(
                select(Listing)
                .where(Listing.id == 301)
                .options(joinedload(Listing.images))
            )

        self.assertIsNotNone(listing)
        self.assertEqual(len(listing.images), 1)
        self.assertTrue(listing.images[0].url.startswith("http"))

    def test_imported_ratings_have_a_broad_seeded_distribution(self):
        with SessionLocal() as db:
            ratings = list(
                db.scalars(
                    select(Listing.rating)
                    .where(Listing.id > 300)
                    .order_by(Listing.id)
                ).all()
            )

        self.assertEqual(len(ratings), 10_000)
        self.assertGreaterEqual(statistics.pstdev(ratings), 0.55)
        self.assertGreaterEqual(sum(rating < 4.0 for rating in ratings), 2_000)
        self.assertLess(sum(rating >= 4.6 for rating in ratings), 4_000)

    def test_imported_stays_seed_early_may_and_support_june_booking(self):
        with SessionLocal() as db:
            anchor_count = db.scalar(
                select(func.count(Availability.id)).where(
                    Availability.listing_id > 300,
                    Availability.date == date(2026, 5, 1),
                    Availability.is_available.is_(True),
                )
            )
            self.assertEqual(anchor_count, 10_000)

            seeded_reservations = db.scalars(
                select(Booking).where(
                    Booking.confirmation_code.startswith(SEEDED_RESERVATION_PREFIX)
                )
            ).all()
            self.assertEqual(
                len(seeded_reservations),
                10_000 * SEEDED_RESERVATIONS_PER_IMPORTED_LISTING,
            )
            self.assertEqual(
                {booking.listing_id for booking in seeded_reservations},
                set(range(301, 10_301)),
            )
            reservations_by_listing: dict[int, list[Booking]] = {}
            for booking in seeded_reservations:
                reservations_by_listing.setdefault(booking.listing_id, []).append(booking)
            self.assertTrue(
                all(
                    len(bookings) == SEEDED_RESERVATIONS_PER_IMPORTED_LISTING
                    for bookings in reservations_by_listing.values()
                )
            )
            self.assertTrue(
                all(
                    booking.guest_id == SEEDED_RESERVATION_GUEST_ID
                    and booking.status == "confirmed"
                    and 2 <= booking.nights <= 10
                    for booking in seeded_reservations
                )
            )
            self.assertTrue(
                all(
                    not (
                        booking.check_out > protected_start
                        and booking.check_in < protected_end
                    )
                    for booking in seeded_reservations
                    for protected_start, protected_end in PROTECTED_STAY_RANGES
                )
            )
            self.assertTrue(
                all(
                    earlier.check_out <= later.check_in
                    for bookings in reservations_by_listing.values()
                    for earlier, later in zip(
                        sorted(bookings, key=lambda booking: booking.check_in),
                        sorted(bookings, key=lambda booking: booking.check_in)[1:],
                    )
                )
            )
            summer_reservations = [
                booking
                for booking in seeded_reservations
                if booking.check_in < date(2026, 9, 1)
                and booking.check_out > date(2026, 6, 1)
            ]
            self.assertEqual(len(summer_reservations), 20_000)
            self.assertEqual(
                len({booking.listing_id for booking in summer_reservations}),
                10_000,
            )
            unavailable_listing_count = db.scalar(
                select(func.count(func.distinct(Availability.listing_id))).where(
                    Availability.listing_id > 300,
                    Availability.is_available.is_(False),
                )
            )
            self.assertEqual(unavailable_listing_count, 10_000)
            late_summer_blackout_count = db.scalar(
                select(func.count(func.distinct(Availability.listing_id))).where(
                    Availability.listing_id > 300,
                    Availability.date >= date(2026, 7, 27),
                    Availability.date < date(2026, 9, 1),
                    Availability.is_available.is_(False),
                )
            )
            self.assertEqual(late_summer_blackout_count, 10_000)

            listing = db.scalar(select(Listing).where(Listing.id == 9760))
            self.assertIsNotNone(listing)
            self.assertEqual(listing.title, "Penthouse with A Stellar View")
            self.assertEqual(listing.city, "Toronto")
            self.assertEqual(listing.price_per_night, 21.08)

            detail = listing_detail(
                self._build_request(f"/listings/{listing.slug}"),
                slug=listing.slug,
                db=db,
            )
            self.assertEqual(detail.context["first_available_date"], "2026-05-01")
            calendar = detail.context["availability_calendar"]
            self.assertEqual(calendar["firstAvailableDate"], "2026-05-01")
            self.assertEqual(calendar["initialMonthDate"], "2026-07-01")
            self.assertTrue(calendar["assumeOpenWindow"])
            self.assertTrue(calendar["allowHistoricalDates"])
            self.assertTrue(
                any(
                    day["date"] >= "2026-07-27" and not day["is_available"]
                    for day in calendar["days"]
                )
            )
            listing_body = detail.body.decode("utf-8")
            self.assertIn("Pick check-in and check-out", listing_body)
            self.assertIn("data-calendar-grid", listing_body)
            self.assertIn("data-calendar-popover", listing_body)
            self.assertIn("data-calendar-toggle", listing_body)
            self.assertIn("data-date-picker-payload", listing_body)
            self.assertIn("Unavailable nights are crossed out", listing_body)

            response = book_listing(
                self._build_request(
                    f"/listings/{listing.slug}/book",
                    user_id=1,
                    method="POST",
                ),
                listing_id=listing.id,
                check_in="2026-06-05",
                check_out="2026-06-07",
                guests=1,
                db=db,
            )
            self.assertEqual(response.status_code, 303)
            booking = db.scalar(
                select(Booking).where(
                    Booking.listing_id == listing.id,
                    Booking.guest_id == 1,
                    Booking.check_in == date(2026, 6, 5),
                    Booking.check_out == date(2026, 6, 7),
                    Booking.status == "confirmed",
                )
            )
            self.assertIsNotNone(booking)

            blocked_listing = db.scalar(select(Listing).where(Listing.id == 301))
            blocked_reservation = min(
                (
                    booking
                    for booking in reservations_by_listing[blocked_listing.id]
                    if booking.check_in >= date(2026, 7, 27)
                    and booking.check_out <= date(2026, 9, 1)
                ),
                key=lambda booking: booking.check_in,
            )
            blocked_response = book_listing(
                self._build_request(
                    f"/listings/{blocked_listing.slug}/book",
                    user_id=1,
                    method="POST",
                ),
                listing_id=blocked_listing.id,
                check_in=blocked_reservation.check_in.isoformat(),
                check_out=blocked_reservation.check_out.isoformat(),
                guests=1,
                db=db,
            )
            self.assertEqual(blocked_response.status_code, 303)
            self.assertIn(
                "Those%20dates%20are%20not%20fully%20available",
                blocked_response.headers["location"],
            )

    def test_manifest_allocation_is_complete_and_proportional(self):
        manifest_path = Path(__file__).resolve().parents[1] / "data" / "inside_airbnb_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["sample_size"], 10_000)
        self.assertEqual(sum(item["sample_count"] for item in manifest["strata"]), 10_000)
        self.assertTrue(all(item["sample_count"] >= 1 for item in manifest["strata"] if item["population_count"]))

        ordered = sorted(
            (item["population_count"], item["sample_count"])
            for item in manifest["strata"]
            if item["population_count"]
        )
        self.assertTrue(
            all(left_sample <= right_sample for (_, left_sample), (_, right_sample) in zip(ordered, ordered[1:]))
        )

    def test_booking_task_evaluator_detects_completed_goal(self):
        with SessionLocal() as db:
            db.add(
                Booking(
                    confirmation_code="BKG-2999",
                    listing_id=1,
                    guest_id=1,
                    check_in=datetime.strptime("2026-04-14", "%Y-%m-%d").date(),
                    check_out=datetime.strptime("2026-04-17", "%Y-%m-%d").date(),
                    guests=2,
                    total_price=815,
                    status="confirmed",
                    created_at=datetime.utcnow(),
                )
            )
            db.commit()

            task = db.scalar(
                select(TaskDefinition).where(TaskDefinition.id == 1).options(joinedload(TaskDefinition.persona))
            )
            result = evaluate_task(db, task)
            self.assertTrue(result["success"])

    def test_all_tasks_start_incomplete_and_are_feasible_through_their_ui_actions(self):
        actions = {
            1: lambda request, db: book_listing(
                request, listing_id=1, check_in="2026-04-14", check_out="2026-04-17", guests=2, db=db
            ),
            2: lambda request, db: toggle_wishlist(request, listing_id=3, db=db),
            3: lambda request, db: send_listing_message(
                request,
                listing_id=2,
                subject="Arrival question",
                body="Could we arrange early check-in?",
                db=db,
            ),
            4: lambda request, db: block_listing_dates(
                request, listing_id=1, start_date="2026-05-08", end_date="2026-05-10", db=db
            ),
            5: lambda request, db: cancel_booking(request, booking_id=1, db=db),
            6: lambda request, db: book_listing(
                request, listing_id=6, check_in="2026-05-01", check_out="2026-05-04", guests=4, db=db
            ),
            7: lambda request, db: toggle_wishlist(request, listing_id=1, db=db),
            8: lambda request, db: send_listing_message(
                request,
                listing_id=4,
                subject="Bike question",
                body="Can you confirm the bike storage setup?",
                db=db,
            ),
            9: lambda request, db: block_listing_dates(
                request, listing_id=2, start_date="2026-05-18", end_date="2026-05-21", db=db
            ),
            10: lambda request, db: cancel_booking(request, booking_id=3, db=db),
        }

        with SessionLocal() as db:
            tasks = db.scalars(
                select(TaskDefinition).options(joinedload(TaskDefinition.persona)).order_by(TaskDefinition.id)
            ).all()
            self.assertEqual([task.id for task in tasks], list(range(1, 11)))

            for task in tasks:
                with self.subTest(task=task.slug):
                    self.assertEqual(task.persona.password, "demo123")
                    self.assertFalse(evaluate_task(db, task)["success"], "task must not start pre-completed")
                    if task.start_path.startswith("/listings/"):
                        slug = task.start_path.removeprefix("/listings/")
                        self.assertIsNotNone(db.scalar(select(Listing.id).where(Listing.slug == slug)))

                    request = self._build_request(task.start_path, user_id=task.persona_user_id, method="POST")
                    response = actions[task.id](request, db)
                    self.assertEqual(response.status_code, 303)
                    self.assertTrue(evaluate_task(db, task)["success"])

    def test_merge_ranges_combines_overlapping_blocks(self):
        merged = merge_ranges(
            [
                {"start": "2026-05-08", "end": "2026-05-10"},
                {"start": "2026-05-09", "end": "2026-05-12"},
                {"start": "2026-06-01", "end": "2026-06-03"},
            ]
        )
        self.assertEqual(
            merged,
            [
                {"start": "2026-05-08", "end": "2026-05-12"},
                {"start": "2026-06-01", "end": "2026-06-03"},
            ],
        )

    def test_optional_search_filters_ignore_empty_strings(self):
        self.assertIsNone(_parse_optional_int(""))
        self.assertIsNone(_parse_optional_int("   "))
        self.assertIsNone(_parse_optional_float(""))
        self.assertEqual(_parse_optional_int("4"), 4)
        self.assertEqual(_parse_optional_float("4.5"), 4.5)

    def test_generic_home_stays_use_house_category(self):
        with SessionLocal() as db:
            listing = db.scalar(
                select(Listing).where(Listing.slug == "montreal-plateau-book-nook")
            )
            self.assertIsNotNone(listing)
            self.assertEqual(get_listing_property_category(listing), "House")

            search_response = home(
                self._build_request("/?property_type=House&sort=price_low"),
                property_type="House",
                sort="price_low",
                db=db,
            )
            self.assertEqual(search_response.context["results_count"], 10_295)
            self.assertIn("House", search_response.context["property_types"])
            self.assertNotIn("Home", search_response.context["property_types"])

    def test_host_dashboard_renders_host_management_sections(self):
        with SessionLocal() as db:
            response = host_dashboard(self._build_request("/host", user_id=2), db)
            body = response.body.decode()

        self.assertIn("Manage listings and reservations", body)
        self.assertIn("Existing blocks", body)
        self.assertIn("Upcoming reservations", body)
        self.assertIn("Annex Glass Loft", body)
        self.assertIn('min="2026-04-01"', body)

    def test_block_listing_dates_updates_host_calendar_and_redirects(self):
        with SessionLocal() as db:
            response = block_listing_dates(
                request=self._build_request("/host/listings/1/block", user_id=2, method="POST"),
                listing_id=1,
                start_date="2026-04-04",
                end_date="2026-04-07",
                db=db,
            )
            listing = db.get(Listing, 1)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/host?notice=Blocked%20dates%20on%20Annex%20Glass%20Loft.")
        self.assertEqual(
            listing.blocked_ranges,
            [
                {"start": "2026-04-03", "end": "2026-04-07"},
                {"start": "2026-06-12", "end": "2026-06-15"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
