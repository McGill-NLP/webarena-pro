"""Currency exchange rate endpoint."""

from fastapi import APIRouter

from ..config import CURRENCY_SYMBOLS, EXCHANGE_RATES

router = APIRouter(prefix="/api/currency", tags=["currency"])


@router.get("/rates")
async def get_rates():
    """Return all exchange rates (USD base) with symbols."""
    return {
        "base": "USD",
        "rates": EXCHANGE_RATES,
        "symbols": CURRENCY_SYMBOLS,
    }
