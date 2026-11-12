export type CabinClass = 'economy' | 'premium_economy' | 'business' | 'first';
export type TripType = 'one_way' | 'round_trip' | 'multi_city';
export type SortBy = 'best' | 'cheapest' | 'fastest';

export interface AutocompleteResult {
  iata: string;
  name: string;
  city_name: string;
  country: string;
  display_name: string;
  hub_score: number;
}

export interface FlightSegment {
  airline_code: string;
  airline_name: string;
  flight_number: string;
  aircraft: string;
  origin: string;
  origin_city: string;
  destination: string;
  destination_city: string;
  departure: string;
  arrival: string;
  duration_minutes: number;
  is_overnight: boolean;
  // Amenities
  legroom_inches: number;
  has_wifi: boolean;
  wifi_type: string | null;
  has_power: boolean;
  has_usb: boolean;
  has_video: boolean;
  video_type: string | null;
}

export interface LayoverInfo {
  duration_minutes: number;
  airport: string;
  airport_city: string;
  is_overnight: boolean;
  is_short_connection: boolean;
}

export interface FlightOffer {
  id: string;
  segments: FlightSegment[];
  layovers: LayoverInfo[];
  total_duration_minutes: number;
  stops: number;
  price_usd: number;
  cabin_class: CabinClass;
  origin: string;
  destination: string;
  departure: string;
  arrival: string;
  emissions_kg: number;
  is_best: boolean;
}

export interface SearchLeg {
  origin: string;
  destination: string;
  date: string; // YYYY-MM-DD
}

export interface Passengers {
  adults: number;
  children: number;
  infants: number;
}

export interface Filters {
  max_stops?: number | null;
  max_price?: number | null;
  max_duration_minutes?: number | null;
  airlines?: string[] | null;
  departure_time_min?: string | null;
  departure_time_max?: string | null;
}

export interface SearchRequest {
  trip_type: TripType;
  legs: SearchLeg[];
  passengers: Passengers;
  cabin_class: CabinClass;
  filters: Filters;
  sort_by: SortBy;
}

export interface SearchResponse {
  outbound_flights: FlightOffer[];
  return_flights: FlightOffer[];
  multi_city_flights: FlightOffer[][];  // one array per leg for multi-city
  search_id: string;
  origin: string;
  destination: string;
  same_airline_discount: number;
}

export interface CalendarDay {
  date: string;
  cheapest_price: number | null;
}

export interface CalendarResponse {
  origin: string;
  destination: string;
  year: number;
  month: number;
  days: CalendarDay[];
}

// --- Booking ---

export interface PassengerInfo {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
}

export interface PaymentInfo {
  card_number: string;
  expiry_date: string; // MM/YY
  cvv: string;
  cardholder_name: string;
}

export interface BookingRequest {
  passenger: PassengerInfo;
  payment: PaymentInfo;
  outbound_flight: FlightOffer;
  return_flight?: FlightOffer | null;
  multi_city_flights?: FlightOffer[];
  total_price?: number;
}

// --- Geolocation & Currency ---

export interface NearestAirport {
  iata: string;
  name: string;
  city: string;
  distance_km: number;
}

export interface GeolocationResponse {
  country_code: string;
  city: string;
  lat: number;
  lon: number;
  currency: string;
  nearest_airports: NearestAirport[];
}

export interface CurrencyRatesResponse {
  base: string;
  rates: Record<string, number>;
  symbols: Record<string, string>;
}

export interface DestinationCard {
  iata: string;
  city: string;
  country: string;
  country_code: string;
  price_usd: number;
  cheapest_date: string; // YYYY-MM-DD
  hub_score?: number;
  distance_km: number;
  is_domestic: boolean;
}

export interface PopularDestinationsResponse {
  origin: string;
  destinations: DestinationCard[];
}

export interface CheapFlightsResponse {
  origin: string;
  category: string;
  flights: DestinationCard[];
}

export interface ConfigResponse {
  benchmark_mode: boolean;
  benchmark_date: string | null;
}

export interface BookingResponse {
  booking_id: string;
  status: string;
  booked_at: string;
  passenger: PassengerInfo;
  payment_summary: {
    card_type: string;
    masked_card: string;
    cardholder_name: string;
  };
  outbound_flight: FlightOffer;
  return_flight?: FlightOffer | null;
  multi_city_flights?: FlightOffer[];
  total_price: number;
}
