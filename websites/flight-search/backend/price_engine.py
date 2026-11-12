"""Fare calculation engine.

==========================================================================
PRICING OVERVIEW
==========================================================================

Every flight price is computed from a deterministic formula with 7
multipliers applied to a distance-based base fare.  Additional discounts
are applied at the itinerary level for connecting flights and round trips.

--------------------------------------------------------------------------
1. BASE FARE
--------------------------------------------------------------------------
    base_usd = BASE_FIXED_USD + (distance_km * BASE_PER_KM_USD)
             = 40 + (distance_km * 0.08)

    Rationale: $40 fixed cost covers airport fees/taxes; $0.08/km covers
    fuel and operating cost.  A 5,000 km flight has base = $440.

--------------------------------------------------------------------------
2. PER-FLIGHT MULTIPLIERS  (applied multiplicatively)
--------------------------------------------------------------------------
    final = base * M_class * M_day * M_time * M_season * M_demand
                 * M_advance * M_jitter

    2a. Cabin class (M_class)
        economy        1.0x
        premium_econ   1.6x
        business       3.2x
        first          5.5x

    2b. Day of week (M_day)  — based on departure date's weekday
        Mon–Wed        0.90x   (mid-week discount)
        Thu            1.00x
        Fri            1.15x   (weekend premium)
        Sat            1.05x
        Sun            1.10x

    2c. Time of day (M_time)  — based on departure hour (local time)
        06:00–08:00    1.10x   (morning rush)
        09:00–15:00    1.00x   (off-peak)
        16:00–19:00    1.15x   (evening rush)
        22:00–05:00    0.85x   (red-eye discount)

    2d. Seasonality (M_season)  — based on departure month
        Jan, Feb       0.85x   (winter off-season)
        Mar            0.95x
        Apr            1.00x
        May            1.05x
        Jun            1.15x   (summer peak)
        Jul            1.20x   (summer peak)
        Aug            1.15x   (summer peak)
        Sep            0.90x   (shoulder season)
        Oct            0.95x
        Nov            1.00x
        Dec            1.40x   (Christmas peak)

        EU summer bonus: flights to European airports (continent="EU")
        during Jun–Aug get an extra +0.15 added to the season multiplier.

    2e. Route demand (M_demand)  — based on carrier competition
        1 carrier      1.20x   (monopoly surcharge)
        2–3 carriers   1.00x
        4+ carriers    0.95x   (high-competition discount)

    2f. Advance booking (M_advance)  — days between booking and departure
        0–3 days       1.50x   (last-minute premium)
        4–7 days       1.35x
        8–14 days      1.20x
        15–21 days     1.10x
        22–60 days     1.00x   (sweet spot)
        61–90 days     0.90x   (early-bird discount)
        91+ days       0.95x   (far-out, slight premium vs sweet spot)

    2g. Seeded jitter (M_jitter)  — deterministic per-flight randomness
        1.0 ± 0.08  (±8%, drawn from uniform distribution)
        Uses SHA-256 seeded RNG so same search → same jitter.

    Minimum price floor: $25 (after all multipliers and surcharges).

    2h. Short-distance surcharge  — flat fee for very short flights
        Routes ≤ 500 km get +$50–$150 (random, deterministic per flight).
        Waived when the leg is part of a connecting itinerary.
        Still applies to round-trip flights (each direction independently).

--------------------------------------------------------------------------
3. ITINERARY-LEVEL DISCOUNTS
--------------------------------------------------------------------------

    3a. Connecting-flight base discount
        Each leg of a multi-segment itinerary is priced individually
        using the formula above, then multiplied by CONNECTING_BASE_DISCOUNT
        (0.75).  This gives a 25% per-leg discount vs buying each segment
        as a separate one-way ticket — simulating how airlines sell
        through-fares cheaper than two one-ways.

    3b. Same-airline connection discount
        If ALL segments of a connecting itinerary are operated by the
        SAME carrier, the total price is further multiplied by
        SAME_AIRLINE_CONNECTION_DISCOUNT (0.88), giving an extra 12%
        off on top of the base connection discount.

        Combined effect: each leg at 0.75, then total * 0.88 =
        effective ~34% discount vs separate one-ways on same carrier.

        Rationale: airlines offer lower fares when they control the
        entire itinerary (no interline agreement needed, guaranteed
        connections, single PNR).

    3c. Round-trip same-airline discount
        After generating both outbound and return flights for a round-trip
        search, return flights that share at least one carrier with ANY
        outbound flight get multiplied by ROUND_TRIP_SAME_AIRLINE_DISCOUNT
        (0.92), giving an 8% discount on the return leg.

        Rationale: airlines incentivize round-trip bookings on their own
        metal.  A passenger who flies AA outbound and AA return pays less
        per leg than mixing carriers.

--------------------------------------------------------------------------
4. CALENDAR PRICING
--------------------------------------------------------------------------
    The calendar endpoint (/api/calendar) shows the cheapest representative
    price per day.  It uses compute_price() with:
        - departure_hour = 12 (noon, off-peak → M_time = 1.00)
        - booking_date = target_date - 14 days (M_advance = 1.20)
    This gives a "typical" price that varies only by day-of-week and
    season, useful for the date-picker price overlay.

==========================================================================
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from .config import (
    ADVANCE_MULTIPLIERS,
    BASE_FIXED_USD,
    BASE_PER_KM_USD,
    CLASS_MULTIPLIERS,
    DAY_MULTIPLIERS,
    EU_CONTINENTS,
    EU_SUMMER_BONUS,
    EU_SUMMER_MONTHS,
    HIGH_COMPETITION_DISCOUNT,
    JITTER_RANGE,
    MONOPOLY_ROUTE_BONUS,
    SEASON_MULTIPLIERS,
    SHORT_DISTANCE_FEE_MAX,
    SHORT_DISTANCE_FEE_MIN,
    SHORT_DISTANCE_THRESHOLD_KM,
)


def compute_price(
    distance_km: int,
    cabin_class: str,
    departure_date: date,
    departure_hour: int,
    num_carriers: int,
    dest_continent: str,
    rng: random.Random,
    booking_date: date | None = None,
    is_connection: bool = False,
) -> float:
    """Compute a single-flight price using the 7-multiplier formula.

    This is the core pricing function.  It computes the fare for one
    segment (one takeoff–landing pair).  Itinerary-level discounts
    (connection, round-trip) are applied separately by the caller.

    Args:
        distance_km:     Great-circle distance of the route.
        cabin_class:     One of "economy", "premium_economy", "business", "first".
        departure_date:  Date of departure (affects day-of-week, season).
        departure_hour:  Hour of departure in local time 0–23 (affects time-of-day).
        num_carriers:    Number of airlines operating this route (affects demand).
        dest_continent:  Destination airport continent code (for EU summer bonus).
        rng:             Seeded Random instance (for deterministic jitter).
        booking_date:    Date of booking (defaults to today; affects advance multiplier).
        is_connection:   True when this leg is part of a connecting itinerary
                         (suppresses the short-distance surcharge).

    Returns:
        Price in USD, rounded to nearest dollar, minimum $25.
    """
    # --- Base fare ---
    base = BASE_FIXED_USD + (distance_km * BASE_PER_KM_USD)

    # --- Multiplier 1: Cabin class ---
    class_mult = CLASS_MULTIPLIERS.get(cabin_class, 1.0)

    # --- Multiplier 2: Day of week ---
    day_mult = DAY_MULTIPLIERS.get(departure_date.weekday(), 1.0)

    # --- Multiplier 3: Time of day ---
    if 6 <= departure_hour <= 8:
        time_mult = 1.10  # Morning peak
    elif 16 <= departure_hour <= 19:
        time_mult = 1.15  # Evening peak
    elif departure_hour >= 22 or departure_hour <= 5:
        time_mult = 0.85  # Red-eye discount
    else:
        time_mult = 1.00

    # --- Multiplier 4: Seasonality ---
    season_mult = SEASON_MULTIPLIERS.get(departure_date.month, 1.0)
    if dest_continent in EU_CONTINENTS and departure_date.month in EU_SUMMER_MONTHS:
        season_mult += EU_SUMMER_BONUS

    # --- Multiplier 5: Route demand (carrier competition) ---
    if num_carriers == 1:
        demand_mult = 1.0 + MONOPOLY_ROUTE_BONUS
    elif num_carriers >= 4:
        demand_mult = 1.0 - HIGH_COMPETITION_DISCOUNT
    else:
        demand_mult = 1.0

    # --- Multiplier 6: Advance booking ---
    if booking_date is None:
        from .benchmark import today
        booking_date = today()
    days_advance = max(0, (departure_date - booking_date).days)
    advance_mult = 1.0
    for threshold, mult in ADVANCE_MULTIPLIERS:
        if days_advance <= threshold:
            advance_mult = mult
            break

    # --- Multiplier 7: Seeded jitter (±8%) ---
    jitter = 1.0 + rng.uniform(-JITTER_RANGE, JITTER_RANGE)

    price = (base * class_mult * day_mult * time_mult
             * season_mult * demand_mult * advance_mult * jitter)

    # Short-distance surcharge: random $50–$150 fee on very short flights.
    # Waived when the leg is part of a connecting itinerary.
    if distance_km <= SHORT_DISTANCE_THRESHOLD_KM and not is_connection:
        price += rng.randint(SHORT_DISTANCE_FEE_MIN, SHORT_DISTANCE_FEE_MAX)

    return max(25.0, round(price, 0))


def compute_calendar_price(
    distance_km: int,
    cabin_class: str,
    target_date: date,
    num_carriers: int,
    dest_continent: str,
    rng: random.Random,
) -> float:
    """Compute the cheapest representative price for a given date.

    Used by the calendar endpoint to show day-by-day pricing.
    Assumes noon departure (off-peak) and 14-day advance booking
    to give a stable "typical" price that varies only by day-of-week
    and season.
    """
    return compute_price(
        distance_km=distance_km,
        cabin_class=cabin_class,
        departure_date=target_date,
        departure_hour=12,
        num_carriers=num_carriers,
        dest_continent=dest_continent,
        rng=rng,
        booking_date=target_date - timedelta(days=14),
    )
