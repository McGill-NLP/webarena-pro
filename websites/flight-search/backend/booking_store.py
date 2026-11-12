"""In-memory user/payment database and booking storage."""

from __future__ import annotations

import uuid
from datetime import datetime

from .benchmark import utcnow as _benchmark_utcnow

# Pre-defined cardholders with payment methods (keyed by lowercase name)
CARDHOLDERS: dict[str, list[dict]] = {
    "jane smith": [
        {"card_number": "4111111111111111", "expiry": "12/27", "cvv": "123", "type": "Visa"},
        {"card_number": "5500005555555559", "expiry": "08/26", "cvv": "456", "type": "Mastercard"},
        {"card_number": "371449635398431", "expiry": "03/28", "cvv": "7890", "type": "Amex"},
    ],
    "john smith": [
        {"card_number": "4111111111111111", "expiry": "12/27", "cvv": "123", "type": "Visa"},
        {"card_number": "4532015112830366", "expiry": "05/26", "cvv": "789", "type": "Visa"},
        {"card_number": "5500000000000004", "expiry": "06/28", "cvv": "456", "type": "Mastercard"},
    ],
    "jane doe": [
        {"card_number": "340000000000009", "expiry": "03/27", "cvv": "7890", "type": "Amex"},
    ],
    "bob wilson": [
        {"card_number": "4012888888881881", "expiry": "09/26", "cvv": "321", "type": "Visa"},
    ],
}

GENERIC_ERROR = "Payment failed. Please check your card details and try again."

# Confirmed bookings stored in memory
_bookings: list[dict] = []


def _normalize_expiry(expiry: str) -> str:
    """Normalize expiry to MM/YY format. Accepts '1227', '12/27', or '12/2027'."""
    raw = expiry.replace("/", "").replace("-", "").strip()
    if len(raw) == 6 and raw.isdigit() and raw[2:4] == "20":
        return f"{raw[:2]}/{raw[4:]}"
    if len(raw) == 4 and raw.isdigit():
        return f"{raw[:2]}/{raw[2:]}"
    return expiry


def _normalize_card_number(card_number: str) -> str:
    """Keep only digits so copied numbers with spaces or dashes still work."""
    return "".join(ch for ch in card_number if ch.isdigit())


def validate_payment(cardholder_name: str, card_number: str, expiry: str, cvv: str) -> tuple[bool, str, str | None]:
    """Validate payment against stored cardholder data.

    Returns (success, error_message, card_type).
    """
    cards = CARDHOLDERS.get(cardholder_name.strip().lower())
    if not cards:
        return False, GENERIC_ERROR, None

    normalized_card_number = _normalize_card_number(card_number)
    normalized_expiry = _normalize_expiry(expiry)

    for card in cards:
        if (
            card["card_number"] == normalized_card_number
            and card["expiry"] == normalized_expiry
            and card["cvv"] == cvv.strip()
        ):
            return True, "", card["type"]

    return False, GENERIC_ERROR, None


def create_booking(booking_data: dict) -> dict:
    """Store a confirmed booking and return it with a unique ID."""
    booking = {
        "booking_id": f"BK-{uuid.uuid4().hex[:8].upper()}",
        "status": "confirmed",
        "booked_at": _benchmark_utcnow().isoformat(),
        **booking_data,
    }
    _bookings.append(booking)
    from .eval_state import record_booking
    record_booking(booking)
    return booking


def get_all_bookings() -> list[dict]:
    """Return all confirmed bookings."""
    return list(_bookings)


def reset_bookings() -> None:
    """Clear runtime booking state back to the image baseline."""
    _bookings.clear()
    from .eval_state import reset_evidence
    reset_evidence()
