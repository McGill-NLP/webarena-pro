from __future__ import annotations

from datetime import date, datetime, timedelta
import math
from typing import Iterable
from urllib.parse import quote, urlsplit

from fastapi import Depends, FastAPI, Form, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.content import (
    SITE_CONTENT,
    get_listing_card_meta,
    get_listing_content,
    get_listing_property_category,
)
from app.database import SessionLocal, get_db
from app.models import (
    Availability,
    Booking,
    Listing,
    Message,
    MessageThread,
    Review,
    TaskDefinition,
    User,
    WishlistItem,
)
from app.inside_airbnb_catalog import SEEDED_RESERVATION_PREFIX
from app.seed import (
    daterange,
    ensure_database_seeded,
    parse_date,
    reset_database,
)
from app.tasks import evaluate_task, serialize_task


DEFAULT_CALENDAR_END = date(2027, 4, 1)
DEFAULT_CALENDAR_INITIAL_MONTH = date(2026, 7, 1)


app = FastAPI(
    title=settings.app_name,
    description="A resettable vacation-rental marketplace with booking, messaging, and hosting flows.",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site=settings.session_same_site,
    https_only=settings.session_https_only,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup() -> None:
    ensure_database_seeded()


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return db.get(User, user_id)


def build_context(request: Request, db: Session, **kwargs):
    current_user = get_current_user(request, db)
    return {
        "request": request,
        "current_user": current_user,
        "site_content": SITE_CONTENT,
        "notice": request.query_params.get("notice"),
        **kwargs,
    }


def redirect_with_notice(path: str, notice: str) -> RedirectResponse:
    separator = "&" if "?" in path else "?"
    return RedirectResponse(url=f"{path}{separator}notice={quote(notice)}", status_code=303)


def _safe_notice_target(request: Request) -> str:
    referer = request.headers.get("referer", "")
    if referer:
        parsed = urlsplit(referer)
        path = parsed.path or "/"
        query = f"?{parsed.query}" if parsed.query else ""
        if path.startswith("/"):
            return f"{path}{query}"
    if request.url.path and request.url.path.startswith("/"):
        return request.url.path
    return "/"


def _parse_optional_int(value: str) -> int | None:
    stripped = value.strip()
    if not stripped:
        return None
    return int(stripped)


def _parse_optional_float(value: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    return float(stripped)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=422, content={"detail": exc.errors()})
    return redirect_with_notice(_safe_notice_target(request), "Please check the values you entered and try again.")


def require_login(request: Request, db: Session, next_path: str) -> User | RedirectResponse:
    user = get_current_user(request, db)
    if user is None:
        return RedirectResponse(url=f"/login?next={quote(next_path)}", status_code=303)
    return user


def require_host(request: Request, db: Session, next_path: str) -> User | RedirectResponse:
    user = require_login(request, db, next_path)
    if isinstance(user, RedirectResponse):
        return user
    if not user.is_host:
        return redirect_with_notice("/", "Sign in with a host account to manage listings.")
    return user


def normalize_redirect_target(target: str | None) -> str:
    if not target or not target.startswith("/"):
        return "/"
    return target


def merge_ranges(ranges: list[dict[str, str]]) -> list[dict[str, str]]:
    if not ranges:
        return []
    ordered = sorted(
        [(parse_date(item["start"]), parse_date(item["end"])) for item in ranges],
        key=lambda item: item[0],
    )
    merged: list[tuple[date, date]] = [ordered[0]]
    for start_date, end_date in ordered[1:]:
        previous_start, previous_end = merged[-1]
        if start_date <= previous_end:
            merged[-1] = (previous_start, max(previous_end, end_date))
        else:
            merged.append((start_date, end_date))
    return [{"start": start.isoformat(), "end": end.isoformat()} for start, end in merged]


def is_date_blocked(current_date: date, blocked_ranges: list[dict[str, str]]) -> bool:
    for blocked_range in blocked_ranges:
        start_date = parse_date(blocked_range["start"])
        end_date = parse_date(blocked_range["end"])
        if start_date <= current_date < end_date:
            return True
    return False


def recompute_availability(db: Session, listing: Listing, start_date: date, end_date: date) -> None:
    entries = db.scalars(
        select(Availability).where(
            Availability.listing_id == listing.id,
            Availability.date >= start_date,
            Availability.date < end_date,
        )
    ).all()
    entry_by_date = {entry.date: entry for entry in entries}
    bookings = db.scalars(
        select(Booking).where(
            Booking.listing_id == listing.id,
            Booking.status == "confirmed",
            Booking.check_out > start_date,
            Booking.check_in < end_date,
        )
    ).all()

    booked_dates = set()
    for booking in bookings:
        booked_dates.update(daterange(booking.check_in, booking.check_out))

    for current_date in daterange(start_date, end_date):
        entry = entry_by_date.get(current_date)
        if entry is None:
            entry = Availability(listing_id=listing.id, date=current_date)
            db.add(entry)
        entry.is_available = (
            current_date not in booked_dates and not is_date_blocked(current_date, listing.blocked_ranges)
        )


def get_listing(db: Session, slug: str) -> Listing | None:
    return db.scalar(
        select(Listing)
        .where(Listing.slug == slug)
        .options(
            joinedload(Listing.host),
            selectinload(Listing.images),
            selectinload(Listing.reviews).joinedload(Review.user),
        )
    )


def serialize_state(db: Session) -> dict:
    listings = db.scalars(select(Listing).options(joinedload(Listing.host)).order_by(Listing.id)).all()
    bookings = db.scalars(
        select(Booking)
        .where(~Booking.confirmation_code.startswith(SEEDED_RESERVATION_PREFIX))
        .options(joinedload(Booking.listing), joinedload(Booking.guest))
        .order_by(Booking.id)
    ).all()
    wishlists = db.scalars(
        select(WishlistItem).options(joinedload(WishlistItem.user), joinedload(WishlistItem.listing))
    ).all()
    threads = db.scalars(
        select(MessageThread)
        .options(joinedload(MessageThread.listing), joinedload(MessageThread.host), joinedload(MessageThread.guest))
        .order_by(MessageThread.id)
    ).all()
    return {
        "summary": {
            "users": db.scalar(select(func.count(User.id))) or 0,
            "listings": len(listings),
            "bookings": len(bookings),
            "wishlist_items": len(wishlists),
            "threads": len(threads),
        },
        "bookings": [
            {
                "confirmation_code": booking.confirmation_code,
                "status": booking.status,
                "guest": booking.guest.email,
                "listing": booking.listing.slug,
                "check_in": booking.check_in.isoformat(),
                "check_out": booking.check_out.isoformat(),
            }
            for booking in bookings
        ],
        "wishlists": [
            {
                "user": item.user.email,
                "listing": item.listing.slug,
            }
            for item in wishlists
        ],
        "threads": [
            {
                "id": thread.id,
                "listing": thread.listing.slug,
                "guest": thread.guest.email,
                "host": thread.host.email,
                "subject": thread.subject,
            }
            for thread in threads
        ],
    }


@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    q: str = "",
    city: str = "",
    guests: str = "",
    max_price: str = "",
    min_rating: str = "",
    amenity: str = "",
    property_type: str = "",
    sort: str = "recommended",
    page: int = 1,
    db: Session = Depends(get_db),
):
    try:
        guests_filter = _parse_optional_int(guests)
        max_price_filter = _parse_optional_int(max_price)
        min_rating_filter = _parse_optional_float(min_rating)
    except ValueError:
        return redirect_with_notice("/", "Please use numbers for guests, price, and rating filters.")

    listings = db.scalars(
        select(Listing).options(joinedload(Listing.host), selectinload(Listing.images)).order_by(Listing.id)
    ).all()

    def matches(listing: Listing) -> bool:
        haystack = " ".join(
            [listing.title, listing.city, listing.country, listing.neighborhood, listing.description]
        ).lower()
        return (
            (not q or q.lower() in haystack)
            and (not city or listing.city == city)
            and (guests_filter is None or listing.max_guests >= guests_filter)
            and (max_price_filter is None or listing.price_per_night <= max_price_filter)
            and (min_rating_filter is None or listing.rating >= min_rating_filter)
            and (not amenity or amenity in listing.amenities)
            and (not property_type or get_listing_property_category(listing) == property_type)
        )

    filtered = [listing for listing in listings if matches(listing)]

    if sort == "price_low":
        filtered.sort(key=lambda item: item.price_per_night)
    elif sort == "price_high":
        filtered.sort(key=lambda item: item.price_per_night, reverse=True)
    elif sort == "rating":
        filtered.sort(key=lambda item: (item.rating, item.review_count), reverse=True)
    else:
        filtered.sort(key=lambda item: (item.rating * item.review_count, item.review_count), reverse=True)

    per_page = 60
    total_pages = max(1, math.ceil(len(filtered) / per_page))
    current_page = min(max(page, 1), total_pages)
    page_start = (current_page - 1) * per_page
    page_listings = filtered[page_start : page_start + per_page]

    all_amenities = sorted({amenity_name for listing in listings for amenity_name in listing.amenities})
    property_types = sorted({get_listing_property_category(listing) for listing in listings})
    cities = sorted({listing.city for listing in listings})
    editorial_listings = sorted(
        listings,
        key=lambda item: (item.rating, item.review_count),
        reverse=True,
    )[:3]

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context=build_context(
            request,
            db,
            home_cards=[
                {
                    "listing": listing,
                    "card_meta": get_listing_card_meta(listing),
                }
                for listing in page_listings
            ],
            results_count=len(filtered),
            marketplace_listing_count=len(listings),
            cities=cities,
            amenities=all_amenities,
            property_types=property_types,
            city_count=len(cities),
            current_page=current_page,
            total_pages=total_pages,
            editorial_cards=[
                {
                    "listing": listing,
                    "content": get_listing_content(listing),
                }
                for listing in editorial_listings
            ],
        ),
    )


@app.get("/guide", response_class=HTMLResponse)
def guide(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="guide.html",
        context=build_context(request, db),
    )


@app.post("/reset")
def browser_reset():
    reset_database()
    return redirect_with_notice("/guide", "Environment reset.")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/", db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context=build_context(request, db, next_path=normalize_redirect_target(next)),
    )


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.email == email))
    if user is None or user.password != password:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context=build_context(
                request,
                db,
                error="That email and password combination does not match our records.",
                next_path=normalize_redirect_target(next),
            ),
            status_code=400,
        )
    request.session["user_id"] = user.id
    return redirect_with_notice(normalize_redirect_target(next), f"Signed in as {user.name}.")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect_with_notice("/", "Signed out.")


@app.get("/switch/{user_id}")
def quick_switch(request: Request, user_id: int, next: str = "/", db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        return redirect_with_notice("/", "That account does not exist.")
    request.session["user_id"] = user.id
    return redirect_with_notice(normalize_redirect_target(next), f"Switched to {user.name}.")


@app.get("/listings/{slug}", response_class=HTMLResponse, name="listing_detail")
def listing_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    listing = db.scalar(
        select(Listing)
        .where(Listing.slug == slug)
        .options(
            joinedload(Listing.host),
            selectinload(Listing.images),
            selectinload(Listing.reviews).joinedload(Review.user),
        )
    )
    if listing is None:
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context=build_context(
                request,
                db,
                home_cards=[],
                results_count=0,
                marketplace_listing_count=0,
                cities=[],
                amenities=[],
                city_count=0,
                editorial_cards=[],
            ),
            status_code=404,
        )

    current_user = get_current_user(request, db)
    listing_content = get_listing_content(listing)
    wishlist_item = None
    if current_user is not None:
        wishlist_item = db.scalar(
            select(WishlistItem).where(
                WishlistItem.user_id == current_user.id,
                WishlistItem.listing_id == listing.id,
            )
        )
    availability_entries = db.scalars(
        select(Availability)
        .where(Availability.listing_id == listing.id)
        .order_by(Availability.date)
    ).all()
    next_unavailable = [
        entry
        for entry in availability_entries
        if not entry.is_available and entry.date >= date.today()
    ][:8]
    first_availability = next(
        (entry for entry in availability_entries if entry.is_available),
        None,
    )
    first_available_date = (
        first_availability.date
        if first_availability is not None
        else date.today()
    )
    latest_seeded_date = max(
        (entry.date for entry in availability_entries),
        default=first_available_date,
    )
    calendar_end = max(DEFAULT_CALENDAR_END, latest_seeded_date + timedelta(days=1))
    initial_calendar_date = min(
        max(DEFAULT_CALENDAR_INITIAL_MONTH, first_available_date),
        calendar_end - timedelta(days=1),
    )
    availability_calendar = {
        "days": [
            {
                "date": entry.date.isoformat(),
                "is_available": entry.is_available,
                "nightly_price": listing.price_per_night,
            }
            for entry in availability_entries
        ],
        "firstAvailableDate": first_available_date.isoformat(),
        "initialMonthDate": initial_calendar_date.isoformat(),
        "checkoutBoundaryDate": calendar_end.isoformat(),
        "assumeOpenWindow": True,
        "allowHistoricalDates": True,
        "selectedCheckIn": "",
        "selectedCheckOut": "",
        "showPricing": True,
        "defaultNightlyPrice": listing.price_per_night,
        "emptySummary": "Choose check-in and check-out on the calendar.",
        "emptyDetail": "Unavailable nights are crossed out.",
    }
    nearby_listings = db.scalars(
        select(Listing)
        .where(Listing.id != listing.id)
        .options(joinedload(Listing.host), selectinload(Listing.images))
        .order_by(Listing.rating.desc(), Listing.review_count.desc())
        .limit(3)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="listing.html",
        context=build_context(
            request,
            db,
            listing=listing,
            listing_content=listing_content,
            gallery_images=listing_content["gallery_images"] or [
                {"url": image.url, "alt_text": image.alt_text} for image in listing.images
            ],
            next_unavailable=next_unavailable,
            has_wishlisted=wishlist_item is not None,
            first_available_date=first_available_date.isoformat(),
            availability_calendar=availability_calendar,
            nearby_cards=[
                {
                    "listing": other,
                    "card_meta": get_listing_card_meta(other),
                }
                for other in nearby_listings
            ],
        ),
    )


@app.post("/listings/{listing_id}/book")
def book_listing(
    request: Request,
    listing_id: int,
    check_in: str = Form(...),
    check_out: str = Form(...),
    guests: int = Form(...),
    db: Session = Depends(get_db),
):
    listing = db.get(Listing, listing_id)
    if listing is None:
        return redirect_with_notice("/", "Listing not found.")
    current_user = require_login(request, db, f"/listings/{listing.slug}")
    if isinstance(current_user, RedirectResponse):
        return current_user
    if current_user.id == listing.host_id:
        return redirect_with_notice(f"/listings/{listing.slug}", "Hosts cannot book their own listing.")

    check_in_date = parse_date(check_in)
    check_out_date = parse_date(check_out)
    if check_out_date <= check_in_date:
        return redirect_with_notice(f"/listings/{listing.slug}", "Choose a check-out date after check-in.")
    if guests > listing.max_guests:
        return redirect_with_notice(f"/listings/{listing.slug}", "Guest count exceeds the listing capacity.")

    recompute_availability(db, listing, check_in_date, check_out_date)
    db.flush()
    availability_entries = db.scalars(
        select(Availability).where(
            Availability.listing_id == listing.id,
            Availability.date >= check_in_date,
            Availability.date < check_out_date,
        )
    ).all()
    nights = (check_out_date - check_in_date).days
    if len(availability_entries) != nights or any(not entry.is_available for entry in availability_entries):
        return redirect_with_notice(f"/listings/{listing.slug}", "Those dates are not fully available.")

    next_booking_number = (db.scalar(select(func.max(Booking.id))) or 0) + 2001
    total_price = nights * listing.price_per_night + listing.cleaning_fee + listing.service_fee
    booking = Booking(
        confirmation_code=f"BKG-{next_booking_number}",
        listing_id=listing.id,
        guest_id=current_user.id,
        check_in=check_in_date,
        check_out=check_out_date,
        guests=guests,
        total_price=round(total_price, 2),
        status="confirmed",
        created_at=datetime.utcnow(),
    )
    db.add(booking)
    for availability_entry in availability_entries:
        availability_entry.is_available = False
    db.commit()
    return redirect_with_notice("/trips", f"Booked {listing.title}.")


@app.post("/listings/{listing_id}/wishlist")
def toggle_wishlist(request: Request, listing_id: int, db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if listing is None:
        return redirect_with_notice("/", "Listing not found.")
    current_user = require_login(request, db, f"/listings/{listing.slug}")
    if isinstance(current_user, RedirectResponse):
        return current_user

    existing = db.scalar(
        select(WishlistItem).where(WishlistItem.user_id == current_user.id, WishlistItem.listing_id == listing_id)
    )
    if existing is None:
        db.add(WishlistItem(user_id=current_user.id, listing_id=listing_id))
        notice = f"Saved {listing.title}."
    else:
        db.delete(existing)
        notice = f"Removed {listing.title} from the wishlist."
    db.commit()
    return redirect_with_notice(f"/listings/{listing.slug}", notice)


@app.post("/listings/{listing_id}/message")
def send_listing_message(
    request: Request,
    listing_id: int,
    subject: str = Form("Question about the stay"),
    body: str = Form(...),
    db: Session = Depends(get_db),
):
    listing = db.get(Listing, listing_id)
    if listing is None:
        return redirect_with_notice("/", "Listing not found.")
    current_user = require_login(request, db, f"/listings/{listing.slug}")
    if isinstance(current_user, RedirectResponse):
        return current_user

    thread = db.scalar(
        select(MessageThread).where(
            MessageThread.listing_id == listing_id,
            MessageThread.guest_id == current_user.id,
            MessageThread.host_id == listing.host_id,
        )
    )
    if thread is None:
        thread = MessageThread(
            listing_id=listing_id,
            guest_id=current_user.id,
            host_id=listing.host_id,
            subject=subject.strip() or "Question about the stay",
            last_message_at=datetime.utcnow(),
        )
        db.add(thread)
        db.flush()
    thread.last_message_at = datetime.utcnow()
    db.add(Message(thread_id=thread.id, sender_id=current_user.id, body=body.strip(), created_at=datetime.utcnow()))
    db.commit()
    return redirect_with_notice(f"/inbox?thread_id={thread.id}", "Message sent.")


@app.get("/trips", response_class=HTMLResponse)
def trips(request: Request, db: Session = Depends(get_db)):
    current_user = require_login(request, db, "/trips")
    if isinstance(current_user, RedirectResponse):
        return current_user
    bookings = db.scalars(
        select(Booking)
        .where(Booking.guest_id == current_user.id)
        .options(joinedload(Booking.listing).joinedload(Listing.host), joinedload(Booking.listing).selectinload(Listing.images))
        .order_by(Booking.check_in)
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="trips.html",
        context=build_context(request, db, bookings=bookings),
    )


@app.post("/bookings/{booking_id}/cancel")
def cancel_booking(request: Request, booking_id: int, db: Session = Depends(get_db)):
    current_user = require_login(request, db, "/trips")
    if isinstance(current_user, RedirectResponse):
        return current_user
    booking = db.scalar(
        select(Booking).where(Booking.id == booking_id, Booking.guest_id == current_user.id).options(joinedload(Booking.listing))
    )
    if booking is None:
        return redirect_with_notice("/trips", "Booking not found.")
    if booking.status == "canceled":
        return redirect_with_notice("/trips", "That booking is already canceled.")
    booking.status = "canceled"
    recompute_availability(db, booking.listing, booking.check_in, booking.check_out)
    db.commit()
    return redirect_with_notice("/trips", f"Canceled {booking.confirmation_code}.")


@app.get("/wishlists", response_class=HTMLResponse)
def wishlists(request: Request, db: Session = Depends(get_db)):
    current_user = require_login(request, db, "/wishlists")
    if isinstance(current_user, RedirectResponse):
        return current_user
    items = db.scalars(
        select(WishlistItem)
        .where(WishlistItem.user_id == current_user.id)
        .options(joinedload(WishlistItem.listing).joinedload(Listing.host), joinedload(WishlistItem.listing).selectinload(Listing.images))
    ).all()
    return templates.TemplateResponse(
        request=request,
        name="wishlists.html",
        context=build_context(
            request,
            db,
            wishlist_cards=[
                {
                    "item": item,
                    "card_meta": get_listing_card_meta(item.listing),
                }
                for item in items
            ],
        ),
    )


@app.get("/inbox", response_class=HTMLResponse)
def inbox(request: Request, thread_id: int | None = None, db: Session = Depends(get_db)):
    current_user = require_login(request, db, "/inbox")
    if isinstance(current_user, RedirectResponse):
        return current_user
    threads = db.scalars(
        select(MessageThread)
        .where(or_(MessageThread.guest_id == current_user.id, MessageThread.host_id == current_user.id))
        .options(
            joinedload(MessageThread.listing),
            joinedload(MessageThread.guest),
            joinedload(MessageThread.host),
            selectinload(MessageThread.messages).joinedload(Message.sender),
        )
        .order_by(MessageThread.last_message_at.desc())
    ).all()
    selected_thread = next((thread for thread in threads if thread.id == thread_id), None)
    if selected_thread is None and threads:
        selected_thread = threads[0]
    return templates.TemplateResponse(
        request=request,
        name="inbox.html",
        context=build_context(request, db, threads=threads, selected_thread=selected_thread),
    )


@app.post("/threads/{thread_id}/reply")
def reply_to_thread(request: Request, thread_id: int, body: str = Form(...), db: Session = Depends(get_db)):
    current_user = require_login(request, db, f"/inbox?thread_id={thread_id}")
    if isinstance(current_user, RedirectResponse):
        return current_user
    thread = db.scalar(
        select(MessageThread).where(
            MessageThread.id == thread_id,
            or_(MessageThread.guest_id == current_user.id, MessageThread.host_id == current_user.id),
        )
    )
    if thread is None:
        return redirect_with_notice("/inbox", "Conversation not found.")
    thread.last_message_at = datetime.utcnow()
    db.add(Message(thread_id=thread.id, sender_id=current_user.id, body=body.strip(), created_at=datetime.utcnow()))
    db.commit()
    return redirect_with_notice(f"/inbox?thread_id={thread.id}", "Reply sent.")


@app.get("/host", response_class=HTMLResponse)
def host_dashboard(request: Request, db: Session = Depends(get_db)):
    current_user = require_host(request, db, "/host")
    if isinstance(current_user, RedirectResponse):
        return current_user
    today = date.today()
    calendar_start = db.scalar(select(func.min(Availability.date))) or today
    listings = db.scalars(
        select(Listing)
        .where(Listing.host_id == current_user.id)
        .options(selectinload(Listing.images))
        .order_by(Listing.id)
    ).all()
    reservations = db.scalars(
        select(Booking)
        .join(Listing, Booking.listing_id == Listing.id)
        .where(Listing.host_id == current_user.id)
        .options(joinedload(Booking.guest), joinedload(Booking.listing))
        .order_by(Booking.check_in)
    ).all()
    reservations_by_listing: dict[int, list[Booking]] = {}
    for booking in reservations:
        reservations_by_listing.setdefault(booking.listing_id, []).append(booking)

    confirmed_reservation_count = 0
    blocked_window_count = 0
    upcoming_reservations = [
        booking for booking in reservations if booking.status == "confirmed" and booking.check_out >= today
    ]
    host_cards = []
    for listing in listings:
        listing_reservations = reservations_by_listing.get(listing.id, [])
        confirmed_count = sum(1 for booking in listing_reservations if booking.status == "confirmed")
        confirmed_reservation_count += confirmed_count
        blocked_windows = sorted(listing.blocked_ranges, key=lambda blocked_window: blocked_window["start"])
        blocked_window_count += len(blocked_windows)
        upcoming_listing_reservations = [
            booking for booking in listing_reservations if booking.status == "confirmed" and booking.check_out >= today
        ]
        host_cards.append(
            {
                "listing": listing,
                "blocked_windows": blocked_windows,
                "confirmed_count": confirmed_count,
                "upcoming_count": len(upcoming_listing_reservations),
                "next_arrival": min(
                    (booking.check_in for booking in upcoming_listing_reservations),
                    default=None,
                ),
            }
        )
    return templates.TemplateResponse(
        request=request,
        name="host_dashboard.html",
        context=build_context(
            request,
            db,
            listings=listings,
            reservations=reservations,
            host_cards=host_cards,
            today=today,
            calendar_start=calendar_start,
            blocked_window_count=blocked_window_count,
            confirmed_reservation_count=confirmed_reservation_count,
            upcoming_reservations=upcoming_reservations,
        ),
    )


@app.post("/host/listings/{listing_id}/block")
def block_listing_dates(
    request: Request,
    listing_id: int,
    start_date: str = Form(...),
    end_date: str = Form(...),
    db: Session = Depends(get_db),
):
    current_user = require_host(request, db, "/host")
    if isinstance(current_user, RedirectResponse):
        return current_user
    listing = db.scalar(select(Listing).where(Listing.id == listing_id, Listing.host_id == current_user.id))
    if listing is None:
        return redirect_with_notice("/host", "Listing not found.")
    block_start = parse_date(start_date)
    block_end = parse_date(end_date)
    if block_end <= block_start:
        return redirect_with_notice("/host", "Choose an end date after the start date.")

    listing.blocked_ranges = merge_ranges(
        [*listing.blocked_ranges, {"start": block_start.isoformat(), "end": block_end.isoformat()}]
    )
    recompute_availability(db, listing, block_start, block_end)
    db.commit()
    return redirect_with_notice("/host", f"Blocked dates on {listing.title}.")


@app.get("/api/tasks")
def list_tasks(db: Session = Depends(get_db)):
    tasks = db.scalars(
        select(TaskDefinition).options(joinedload(TaskDefinition.persona)).order_by(TaskDefinition.id)
    ).all()
    return {"tasks": [serialize_task(task) for task in tasks]}


@app.get("/api/tasks/{task_id}")
def task_detail(task_id: int, db: Session = Depends(get_db)):
    task = db.scalar(
        select(TaskDefinition).where(TaskDefinition.id == task_id).options(joinedload(TaskDefinition.persona))
    )
    if task is None:
        return JSONResponse({"error": "Task not found."}, status_code=404)
    return serialize_task(task)


@app.get("/api/tasks/{task_id}/evaluate")
@app.post("/api/tasks/{task_id}/evaluate")
def task_evaluate(task_id: int, db: Session = Depends(get_db)):
    task = db.scalar(
        select(TaskDefinition).where(TaskDefinition.id == task_id).options(joinedload(TaskDefinition.persona))
    )
    if task is None:
        return JSONResponse({"error": "Task not found."}, status_code=404)
    return evaluate_task(db, task)


@app.get("/api/state")
def state(db: Session = Depends(get_db)):
    return serialize_state(db)


@app.post("/api/reset")
def api_reset(token: str = ""):
    if settings.reset_token and token != settings.reset_token:
        return JSONResponse({"error": "Invalid reset token."}, status_code=403)
    reset_database()
    with SessionLocal() as fresh_db:
        return {"status": "ok", "message": "Environment reset.", "state": serialize_state(fresh_db)}


@app.get("/api/eval/state")
def eval_state(request: Request, db: Session = Depends(get_db)):
    """Backend state for the WebArena-Pro evaluator (read-only, token-gated).

    Richer than /api/state: includes booking guest counts, message bodies and
    blocked availability dates. Gated by WP_EVAL_TOKEN so the agent under test
    cannot read answers; disabled (403) when the token is unset.
    """
    import os

    token = os.environ.get("WP_EVAL_TOKEN")
    if not token or request.headers.get("X-Eval-Token") != token:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    bookings = db.scalars(
        select(Booking).options(joinedload(Booking.listing), joinedload(Booking.guest)).order_by(Booking.id)
    ).all()
    wishlists = db.scalars(
        select(WishlistItem).options(joinedload(WishlistItem.user), joinedload(WishlistItem.listing))
    ).all()
    threads = db.scalars(
        select(MessageThread)
        .options(joinedload(MessageThread.listing), joinedload(MessageThread.host), joinedload(MessageThread.guest))
        .order_by(MessageThread.id)
    ).all()
    messages = db.scalars(
        select(Message).options(joinedload(Message.sender)).order_by(Message.id)
    ).all()
    blocked = db.scalars(
        select(Availability)
        .options(joinedload(Availability.listing))
        .where(Availability.is_available.is_(False))
        .order_by(Availability.listing_id, Availability.date)
    ).all()
    return {
        "bookings": [
            {
                "confirmation_code": b.confirmation_code,
                "status": b.status,
                "guest": b.guest.email,
                "listing": b.listing.slug,
                "check_in": b.check_in.isoformat(),
                "check_out": b.check_out.isoformat(),
                "guests": b.guests,
            }
            for b in bookings
        ],
        "wishlists": [
            {"user": item.user.email, "listing": item.listing.slug} for item in wishlists
        ],
        "threads": [
            {
                "id": t.id,
                "listing": t.listing.slug,
                "guest": t.guest.email,
                "host": t.host.email,
                "subject": t.subject,
            }
            for t in threads
        ],
        "messages": [
            {
                "thread_id": m.thread_id,
                "sender": m.sender.email,
                "body": m.body,
            }
            for m in messages
        ],
        "blocked_dates": [
            {"listing": a.listing.slug, "date": a.date.isoformat()} for a in blocked
        ],
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
