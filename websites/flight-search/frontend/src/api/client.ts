import type { AutocompleteResult, BookingRequest, BookingResponse, CalendarResponse, CheapFlightsResponse, ConfigResponse, CurrencyRatesResponse, GeolocationResponse, PopularDestinationsResponse, SearchRequest, SearchResponse } from './types';

const BASE_URL = '/api';

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function getConfig(): Promise<ConfigResponse> {
  return fetchJson<ConfigResponse>(`${BASE_URL}/config`);
}

export async function searchAirports(query: string): Promise<AutocompleteResult[]> {
  if (!query || query.length < 1) return [];
  return fetchJson<AutocompleteResult[]>(
    `${BASE_URL}/airports/autocomplete?q=${encodeURIComponent(query)}`
  );
}

export async function searchFlights(req: SearchRequest): Promise<SearchResponse> {
  return fetchJson<SearchResponse>(`${BASE_URL}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
}

export async function bookFlight(req: BookingRequest): Promise<BookingResponse> {
  const res = await fetch(`${BASE_URL}/booking`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || `Booking failed (${res.status})`);
  }
  return res.json();
}

export async function getCalendar(
  origin: string,
  destination: string,
  year: number,
  month: number,
  cabinClass: string = 'economy'
): Promise<CalendarResponse> {
  return fetchJson<CalendarResponse>(
    `${BASE_URL}/calendar?origin=${origin}&destination=${destination}&year=${year}&month=${month}&cabin_class=${cabinClass}`
  );
}

export async function getGeolocation(): Promise<GeolocationResponse> {
  return fetchJson<GeolocationResponse>(`${BASE_URL}/geolocation`);
}

export async function getCurrencyRates(): Promise<CurrencyRatesResponse> {
  return fetchJson<CurrencyRatesResponse>(`${BASE_URL}/currency/rates`);
}

export async function getPopularDestinations(origin: string, limit: number = 8): Promise<PopularDestinationsResponse> {
  return fetchJson<PopularDestinationsResponse>(
    `${BASE_URL}/destinations/popular?origin=${encodeURIComponent(origin)}&limit=${limit}`
  );
}

export async function getCheapFlights(origin: string, category: string = 'popular', limit: number = 8): Promise<CheapFlightsResponse> {
  return fetchJson<CheapFlightsResponse>(
    `${BASE_URL}/destinations/cheap-flights?origin=${encodeURIComponent(origin)}&category=${category}&limit=${limit}`
  );
}
