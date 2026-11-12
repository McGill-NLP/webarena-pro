"""Pricing constants and configuration."""

# Base price formula
BASE_FIXED_USD = 40
BASE_PER_KM_USD = 0.08

# Cabin class multipliers
CLASS_MULTIPLIERS = {
    "economy": 1.0,
    "premium_economy": 1.6,
    "business": 3.2,
    "first": 5.5,
}

# Day-of-week multipliers (0=Monday, 6=Sunday)
DAY_MULTIPLIERS = {
    0: 0.90,  # Monday
    1: 0.90,  # Tuesday
    2: 0.90,  # Wednesday
    3: 1.00,  # Thursday
    4: 1.15,  # Friday
    5: 1.05,  # Saturday
    6: 1.10,  # Sunday
}

# Season multipliers by month
SEASON_MULTIPLIERS = {
    1: 0.85,   # January - off season
    2: 0.85,   # February - off season
    3: 0.95,   # March
    4: 1.00,   # April
    5: 1.05,   # May
    6: 1.15,   # June - summer peak
    7: 1.20,   # July - summer peak
    8: 1.15,   # August - summer peak
    9: 0.90,   # September - off season
    10: 0.95,  # October
    11: 1.00,  # November
    12: 1.40,  # December - Christmas
}

# Season bonus for EU destinations in summer
EU_SUMMER_BONUS = 0.15  # +15% on top of summer multiplier
EU_CONTINENTS = {"EU"}
EU_SUMMER_MONTHS = {6, 7, 8}

# Demand multipliers
MONOPOLY_ROUTE_BONUS = 0.20      # +20% if only 1 carrier
HIGH_COMPETITION_DISCOUNT = 0.05  # -5% if 4+ carriers

# Advance booking multipliers (days before departure)
ADVANCE_MULTIPLIERS = [
    (3, 1.85),     # 0-3 days: +85% (last-minute premium)
    (7, 1.50),     # 4-7 days: +50%
    (14, 1.20),    # 8-14 days: +20%
    (21, 1.10),    # 15-21 days: +10%
    (60, 1.00),    # 22-60 days: base
    (90, 0.90),    # 61-90 days: -10%
    (float("inf"), 0.95),  # 91+ days: -5%
]

# Short-distance surcharge (flat fee added to very short flights)
# Waived for legs that are part of a connecting itinerary, but NOT for round trips.
SHORT_DISTANCE_THRESHOLD_KM = 500
SHORT_DISTANCE_FEE_MIN = 50
SHORT_DISTANCE_FEE_MAX = 150

# Jitter range (±8%)
JITTER_RANGE = 0.08

# Hub detection thresholds
HUB_MIN_ROUTES = 100
HUB_TOP_N = 125

# Connecting flight constraints
MAX_1STOP_DISTANCE_RATIO = 1.8   # Max total distance vs great-circle
MAX_2STOP_DISTANCE_RATIO = 2.5
MAX_LAYOVER_MINUTES = 360        # 6 hours

# Minimum connection time (MCT) by connection type.
# A leg is "domestic" if origin and destination share the same country_code,
# "international" otherwise.  The tuple key is (arriving_leg_type, departing_leg_type).
MIN_CONNECTION_MINUTES: dict[tuple[str, str], int] = {
    ("domestic", "domestic"): 45,          # Same terminal / no customs
    ("domestic", "international"): 75,     # Need international departure processing
    ("international", "domestic"): 90,     # Customs & immigration on arrival
    ("international", "international"): 120,  # Customs + international re-departure
}
# Fallback used when connection type can't be determined
MIN_LAYOVER_MINUTES = 60
# Layovers shorter than this trigger a "Short connection" warning
SHORT_CONNECTION_MINUTES = 90

# Flight generation
MIN_FLIGHTS_PER_DAY = 1
MAX_FLIGHTS_SINGLE_CARRIER = 3
MAX_FLIGHTS_MULTI_CARRIER = 15
DEPARTURE_HOUR_MIN = 5           # 05:00 (fallback only)
DEPARTURE_HOUR_MAX = 23          # 23:00 (fallback only)

# ---------------------------------------------------------------------------
# Realistic departure time distributions by route type
# ---------------------------------------------------------------------------
# Each list has 24 entries (index 0 = midnight, 23 = 11 PM).
# Higher weight = more departures at that hour.
DEPARTURE_WEIGHTS: dict[str, list[int]] = {
    # NA → EU: Evening departures, arrive early morning EU time
    "na_to_eu": [
        0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 2, 2, 2, 3, 4, 5, 8, 12, 15, 14, 10, 7, 4, 1,
    ],
    # EU → NA: Daytime departures, arrive daytime NA
    "eu_to_na": [
        0, 0, 0, 0, 0, 0, 1, 3, 7, 12, 15, 14, 10, 8, 5, 3, 2, 1, 1, 0, 0, 0, 0, 0,
    ],
    # NA → Asia: Late morning / early afternoon departures
    "na_to_asia": [
        0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 5, 12, 15, 14, 10, 7, 4, 2, 1, 0, 0, 0, 0, 0,
    ],
    # Asia → NA: Afternoon departures, arrive same day NA
    "asia_to_na": [
        0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 5, 7, 10, 14, 14, 10, 7, 4, 2, 1, 0, 0, 0, 0,
    ],
    # EU → Asia: afternoon–evening lean
    "eu_to_asia": [
        0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 5, 5, 6, 7, 8, 8, 7, 5, 3, 2, 1, 0,
    ],
    # Asia → EU: late-night departures (23:00–02:30), arrive morning EU
    "asia_to_eu": [
        5, 3, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 3, 8, 14,
    ],
    # Domestic / same-continent: morning rush + evening rush
    "domestic": [
        0, 0, 0, 0, 0, 1, 4, 8, 10, 8, 6, 5, 5, 5, 5, 5, 6, 8, 8, 5, 3, 2, 1, 0,
    ],
    # Default intercontinental: broad daytime bell curve
    "default": [
        0, 0, 0, 0, 0, 1, 3, 5, 7, 8, 8, 7, 6, 6, 6, 6, 6, 6, 5, 4, 3, 2, 1, 0,
    ],
}

# Popularity-based time window limits (num_carriers → earliest, latest hour allowed)
# Routes with fewer carriers get a tighter daytime-only window.
POPULARITY_TIME_LIMITS: list[tuple[int, int, int]] = [
    # (min_carriers, earliest_hour, latest_hour)
    (8, 5, 23),   # Very popular: 5 AM – 11 PM
    (4, 6, 22),   # Popular:      6 AM – 10 PM
    (2, 6, 21),   # Moderate:     6 AM –  9 PM
    (0, 7, 21),   # Low:          7 AM –  9 PM
]

# Midnight–5 AM curfew multiplier by airport size (route count threshold)
# Smaller airports have essentially zero overnight flights; major hubs keep some.
CURFEW_FACTORS: list[tuple[int, float]] = [
    # (min_routes, factor applied to 0:00–5:59 weights)
    (200, 0.25),   # Major hubs
    (100, 0.10),   # Large airports
    (50,  0.04),   # Medium airports
    (0,   0.01),   # Small airports — near-zero
]

# Hub airport bonus to total flight count
HUB_FLIGHT_BONUS: list[tuple[int, int, int]] = [
    # (min_routes, bonus_min, bonus_max)
    (200, 3, 6),
    (100, 1, 4),
    (50,  0, 2),
]

# Route types with intentional late-night / early-morning departures.
# These skip the popularity window and airport curfew so the overnight
# pattern encoded in DEPARTURE_WEIGHTS is preserved.
OVERNIGHT_EXEMPT_ROUTES: set[str] = {"asia_to_eu"}

# Maximum random extension to the popularity latest-hour (in minutes).
# Popular routes can have departures up to this much later than the base limit.
POPULARITY_LATEST_EXTENSION_MAX = 90  # 1.5 hours

# Departure-weight per-hour jitter range (±fraction applied to each hourly weight)
DEPARTURE_WEIGHT_JITTER = 0.20

# Aircraft types by distance
AIRCRAFT_BY_DISTANCE = [
    (500, ["E190", "E175", "CRJ-900"]),
    (2000, ["A320", "A321", "737-800", "737 MAX 8"]),
    (5000, ["A321neo LR", "757-200", "767-300ER"]),
    (10000, ["787-8", "787-9", "A330-300", "A350-900"]),
    (float("inf"), ["777-300ER", "A350-1000", "787-10", "A380"]),
]

# Connection discount (applied per-leg for any connecting itinerary)
CONNECTING_BASE_DISCOUNT = 0.75       # 25% off each leg vs buying separately

# Same-airline connection bonus: additional discount when all segments
# in a connecting itinerary are operated by the same carrier.
# Stacks with CONNECTING_BASE_DISCOUNT: effective = 0.75 * 0.88 = 0.66 (34% off)
SAME_AIRLINE_CONNECTION_DISCOUNT = 0.88  # Extra 12% off on top of base connection discount

# Round-trip same-airline discount: when a return flight is on the same carrier
# as an outbound flight, the return leg gets this multiplier.
# Simulates bundled round-trip fares offered by airlines.
ROUND_TRIP_SAME_AIRLINE_DISCOUNT = 0.92  # 8% off the return leg

# CO2 emissions estimate (kg per passenger per km)
# Source: ICAO Carbon Emissions Calculator methodology
# Economy baseline ~0.09 kg/km, scales with cabin class (more space = more emissions share)
EMISSIONS_KG_PER_KM = {
    "economy": 0.09,
    "premium_economy": 0.13,
    "business": 0.25,
    "first": 0.35,
}

# "Best" flight ranking: top N flights by composite score are tagged is_best=True
BEST_FLIGHTS_COUNT = 3
# Composite score weights for "best" ranking
BEST_WEIGHT_PRICE = 0.45
BEST_WEIGHT_DURATION = 0.35
BEST_WEIGHT_STOPS = 0.20

# Amenity generation rules
# Legroom ranges (inches) by cabin class
LEGROOM_RANGES = {
    "economy": (29, 32),
    "premium_economy": (34, 38),
    "business": (38, 78),
    "first": (78, 86),
}

# WiFi probability by aircraft family (widebody long-haul more likely)
WIFI_AIRCRAFT = {
    "787-8": 0.95, "787-9": 0.95, "787-10": 0.95,
    "A350-900": 0.92, "A350-1000": 0.92,
    "A330-300": 0.70, "777-300ER": 0.85,
    "A380": 0.80,
    "A321neo LR": 0.80, "757-200": 0.50, "767-300ER": 0.60,
    "A320": 0.55, "A321": 0.60, "737-800": 0.50, "737 MAX 8": 0.75,
    "E190": 0.25, "E175": 0.20, "CRJ-900": 0.15,
}

# Power/USB probability by aircraft family
POWER_AIRCRAFT = {
    "787-8": 0.95, "787-9": 0.95, "787-10": 0.95,
    "A350-900": 0.95, "A350-1000": 0.95,
    "A330-300": 0.75, "777-300ER": 0.85,
    "A380": 0.90,
    "A321neo LR": 0.80, "757-200": 0.40, "767-300ER": 0.55,
    "A320": 0.45, "A321": 0.50, "737-800": 0.40, "737 MAX 8": 0.70,
    "E190": 0.15, "E175": 0.10, "CRJ-900": 0.05,
}

# Video probability (seatback IFE) — mostly widebody long-haul
VIDEO_AIRCRAFT = {
    "787-8": 0.90, "787-9": 0.92, "787-10": 0.92,
    "A350-900": 0.93, "A350-1000": 0.93,
    "A330-300": 0.80, "777-300ER": 0.90,
    "A380": 0.95,
    "A321neo LR": 0.40, "757-200": 0.25, "767-300ER": 0.60,
    "A320": 0.10, "A321": 0.12, "737-800": 0.08, "737 MAX 8": 0.15,
    "E190": 0.0, "E175": 0.0, "CRJ-900": 0.0,
}

# Business/first class always get power and higher WiFi/video odds
PREMIUM_CLASS_AMENITY_BOOST = 0.30  # +30% probability for business/first

# Search limits
MAX_RESULTS = 200
MAX_AUTOCOMPLETE_RESULTS = 10

# ---------------------------------------------------------------------------
# Currency exchange rates (USD base)
# ---------------------------------------------------------------------------
EXCHANGE_RATES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 149.50,
    "CAD": 1.36,
    "AUD": 1.53,
    "CHF": 0.88,
    "CNY": 7.24,
    "INR": 83.12,
    "MXN": 17.15,
    "BRL": 4.97,
    "KRW": 1325.0,
    "SGD": 1.34,
    "HKD": 7.82,
    "NOK": 10.55,
    "SEK": 10.42,
    "DKK": 6.88,
    "NZD": 1.63,
    "ZAR": 18.63,
    "THB": 35.50,
    "TWD": 31.50,
    "PLN": 4.02,
    "TRY": 30.25,
    "ILS": 3.67,
    "AED": 3.67,
    "SAR": 3.75,
    "CLP": 925.0,
    "COP": 3950.0,
    "ARS": 830.0,
    "PHP": 55.80,
    "MYR": 4.72,
    "IDR": 15650.0,
    "VND": 24500.0,
    "EGP": 30.90,
    "QAR": 3.64,
    "KWD": 0.31,
    "BHD": 0.38,
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3", "JPY": "\u00a5",
    "CAD": "C$", "AUD": "A$", "CHF": "CHF", "CNY": "\u00a5",
    "INR": "\u20b9", "MXN": "MX$", "BRL": "R$", "KRW": "\u20a9",
    "SGD": "S$", "HKD": "HK$", "NOK": "kr", "SEK": "kr",
    "DKK": "kr", "NZD": "NZ$", "ZAR": "R", "THB": "\u0e3f",
    "TWD": "NT$", "PLN": "z\u0142", "TRY": "\u20ba", "ILS": "\u20aa",
    "AED": "AED", "SAR": "SAR", "CLP": "CLP$", "COP": "COP$",
    "ARS": "ARS$", "PHP": "\u20b1", "MYR": "RM", "IDR": "Rp",
    "VND": "\u20ab", "EGP": "E\u00a3", "QAR": "QAR", "KWD": "KD",
    "BHD": "BD",
}

# Map country codes (ISO 3166-1 alpha-2) to default currency
COUNTRY_CURRENCY_MAP: dict[str, str] = {
    "US": "USD", "GB": "GBP", "DE": "EUR", "FR": "EUR", "IT": "EUR",
    "ES": "EUR", "NL": "EUR", "BE": "EUR", "AT": "EUR", "PT": "EUR",
    "IE": "EUR", "FI": "EUR", "GR": "EUR", "JP": "JPY", "CA": "CAD",
    "AU": "AUD", "CH": "CHF", "CN": "CNY", "IN": "INR", "MX": "MXN",
    "BR": "BRL", "KR": "KRW", "SG": "SGD", "HK": "HKD", "NO": "NOK",
    "SE": "SEK", "DK": "DKK", "NZ": "NZD", "ZA": "ZAR", "TH": "THB",
    "TW": "TWD", "PL": "PLN", "TR": "TRY", "IL": "ILS", "AE": "AED",
    "SA": "SAR", "CL": "CLP", "CO": "COP", "AR": "ARS", "PH": "PHP",
    "MY": "MYR", "ID": "IDR", "VN": "VND", "EG": "EGP", "QA": "QAR",
    "KW": "KWD", "BH": "BHD",
}
