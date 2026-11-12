"""Pydantic models for API request/response contracts."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CabinClass(str, Enum):
    economy = "economy"
    premium_economy = "premium_economy"
    business = "business"
    first = "first"


class TripType(str, Enum):
    one_way = "one_way"
    round_trip = "round_trip"
    multi_city = "multi_city"


class SortBy(str, Enum):
    best = "best"
    cheapest = "cheapest"
    fastest = "fastest"


# --- Airport ---

class AirportInfo(BaseModel):
    iata: str
    name: str
    city_name: str
    country: str
    country_code: str
    continent: str
    latitude: float
    longitude: float
    timezone: str
    hub_score: float = 0.0
    route_count: int = 0


# --- Flight segment ---

class FlightSegment(BaseModel):
    airline_code: str
    airline_name: str
    flight_number: str
    aircraft: str
    origin: str
    origin_city: str
    destination: str
    destination_city: str
    departure: datetime
    arrival: datetime
    duration_minutes: int
    # Overnight: arrival local date > departure local date
    is_overnight: bool = False
    # Amenities
    legroom_inches: int = 31
    has_wifi: bool = False
    wifi_type: Optional[str] = None       # "Free Wi-Fi", "Wi-Fi for a fee"
    has_power: bool = False
    has_usb: bool = False
    has_video: bool = False
    video_type: Optional[str] = None      # "On-demand video", "Live TV", "Seatback screen"


# --- Layover info (one per gap between consecutive segments) ---

class LayoverInfo(BaseModel):
    duration_minutes: int
    airport: str                       # IATA code of layover airport
    airport_city: str
    is_overnight: bool = False         # layover spans different calendar dates (local)
    is_short_connection: bool = False  # layover under SHORT_CONNECTION_MINUTES


# --- Flight offer (may have multiple segments) ---

class FlightOffer(BaseModel):
    id: str
    segments: list[FlightSegment]
    layovers: list[LayoverInfo] = []   # len == max(0, len(segments) - 1)
    total_duration_minutes: int
    stops: int
    price_usd: float
    cabin_class: CabinClass
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    emissions_kg: int = 0
    is_best: bool = False


# --- Search request ---

class SearchLeg(BaseModel):
    origin: str = Field(..., min_length=3, max_length=3, description="IATA code")
    destination: str = Field(..., min_length=3, max_length=3, description="IATA code")
    date: date


class Passengers(BaseModel):
    adults: int = Field(1, ge=1, le=9)
    children: int = Field(0, ge=0, le=9)
    infants: int = Field(0, ge=0, le=4)

    @property
    def total(self) -> int:
        return self.adults + self.children + self.infants


class Filters(BaseModel):
    max_stops: Optional[int] = None
    max_price: Optional[float] = None
    max_duration_minutes: Optional[int] = None
    airlines: Optional[list[str]] = None  # IATA codes to include
    departure_time_min: Optional[str] = None  # "06:00"
    departure_time_max: Optional[str] = None  # "18:00"


class SearchRequest(BaseModel):
    trip_type: TripType = TripType.round_trip
    legs: list[SearchLeg] = Field(..., min_length=1, max_length=6)
    passengers: Passengers = Passengers()
    cabin_class: CabinClass = CabinClass.economy
    filters: Filters = Filters()
    sort_by: SortBy = SortBy.best


class SearchResponse(BaseModel):
    outbound_flights: list[FlightOffer]
    return_flights: list[FlightOffer] = []
    multi_city_flights: list[list[FlightOffer]] = []  # one list per leg for multi-city
    search_id: str
    origin: str
    destination: str
    same_airline_discount: float = 1.0


# --- Calendar ---

class CalendarDay(BaseModel):
    date: date
    cheapest_price: Optional[float] = None


class CalendarResponse(BaseModel):
    origin: str
    destination: str
    year: int
    month: int
    days: list[CalendarDay]


# --- Autocomplete ---

class AutocompleteResult(BaseModel):
    iata: str
    name: str
    city_name: str
    country: str
    display_name: str
    hub_score: float = 0.0


# --- Booking ---

class PassengerInfo(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str


class PaymentInfo(BaseModel):
    card_number: str
    expiry_date: str  # MM/YY
    cvv: str
    cardholder_name: str


class BookingFlightInfo(BaseModel):
    id: str
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    total_duration_minutes: int
    stops: int
    price_usd: float
    cabin_class: CabinClass
    segments: list[FlightSegment]


class BookingRequest(BaseModel):
    passenger: PassengerInfo
    payment: PaymentInfo
    outbound_flight: BookingFlightInfo
    return_flight: Optional[BookingFlightInfo] = None
    multi_city_flights: list[BookingFlightInfo] = []  # for multi-city bookings
    total_price: Optional[float] = None  # final price from frontend (includes discounts + fare tier)


class BookingResponse(BaseModel):
    booking_id: str
    status: str
    booked_at: str
    passenger: PassengerInfo
    payment_summary: dict
    outbound_flight: BookingFlightInfo
    return_flight: Optional[BookingFlightInfo] = None
    multi_city_flights: list[BookingFlightInfo] = []
    total_price: float
