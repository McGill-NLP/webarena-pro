"""Booking API — validate payment and create bookings."""

from fastapi import APIRouter, HTTPException

from ..booking_store import create_booking, get_all_bookings, validate_payment
from ..models import BookingRequest, BookingResponse

router = APIRouter(prefix="/api", tags=["booking"])


@router.post("/booking", response_model=BookingResponse)
async def book_flight(req: BookingRequest):
    """Validate payment and create a confirmed booking."""
    ok, error_msg, card_type = validate_payment(
        cardholder_name=req.payment.cardholder_name,
        card_number=req.payment.card_number,
        expiry=req.payment.expiry_date,
        cvv=req.payment.cvv,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=error_msg)

    if req.total_price is not None:
        total_price = req.total_price
    elif req.multi_city_flights:
        total_price = sum(f.price_usd for f in req.multi_city_flights)
    else:
        total_price = req.outbound_flight.price_usd
        if req.return_flight:
            total_price += req.return_flight.price_usd

    # Mask card number for response
    masked_card = "****" + req.payment.card_number[-4:]

    booking = create_booking({
        "passenger": req.passenger.model_dump(),
        "payment_summary": {
            "card_type": card_type,
            "masked_card": masked_card,
            "cardholder_name": req.payment.cardholder_name,
        },
        "outbound_flight": req.outbound_flight.model_dump(mode="json"),
        "return_flight": req.return_flight.model_dump(mode="json") if req.return_flight else None,
        "multi_city_flights": [f.model_dump(mode="json") for f in req.multi_city_flights] if req.multi_city_flights else [],
        "total_price": total_price,
    })
    return booking


@router.get("/bookings")
async def list_bookings():
    """List all confirmed bookings."""
    return get_all_bookings()
