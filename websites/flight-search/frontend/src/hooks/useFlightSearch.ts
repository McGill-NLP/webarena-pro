import { useCallback, useState } from 'react';
import { searchFlights } from '../api/client';
import type { CabinClass, Filters, FlightOffer, Passengers, SearchLeg, SearchRequest, SortBy, TripType } from '../api/types';

interface SearchState {
  outboundFlights: FlightOffer[];
  returnFlights: FlightOffer[];
  multiCityFlights: FlightOffer[][];
  sameAirlineDiscount: number;
  loading: boolean;
  error: string | null;
  searched: boolean;
}

export function useFlightSearch() {
  const [state, setState] = useState<SearchState>({
    outboundFlights: [],
    returnFlights: [],
    multiCityFlights: [],
    sameAirlineDiscount: 1.0,
    loading: false,
    error: null,
    searched: false,
  });

  const search = useCallback(async (params: {
    tripType: TripType;
    origin: string;
    destination: string;
    departureDate: string;
    returnDate?: string;
    passengers: Passengers;
    cabinClass: CabinClass;
    filters: Filters;
    sortBy: SortBy;
    multiCityLegs?: SearchLeg[];
  }) => {
    setState(s => ({ ...s, loading: true, error: null }));

    let legs: SearchLeg[];
    if (params.tripType === 'multi_city' && params.multiCityLegs && params.multiCityLegs.length >= 2) {
      legs = params.multiCityLegs;
    } else {
      legs = [{ origin: params.origin, destination: params.destination, date: params.departureDate }];
      if (params.tripType === 'round_trip' && params.returnDate) {
        legs.push({ origin: params.destination, destination: params.origin, date: params.returnDate });
      }
    }

    const req: SearchRequest = {
      trip_type: params.tripType,
      legs,
      passengers: params.passengers,
      cabin_class: params.cabinClass,
      filters: params.filters,
      sort_by: params.sortBy,
    };

    try {
      const res = await searchFlights(req);
      setState({
        outboundFlights: res.outbound_flights,
        returnFlights: res.return_flights,
        multiCityFlights: res.multi_city_flights || [],
        sameAirlineDiscount: res.same_airline_discount ?? 1.0,
        loading: false,
        error: null,
        searched: true,
      });
    } catch (err) {
      setState({
        outboundFlights: [],
        returnFlights: [],
        multiCityFlights: [],
        sameAirlineDiscount: 1.0,
        loading: false,
        error: err instanceof Error ? err.message : 'Search failed',
        searched: true,
      });
    }
  }, []);

  return { ...state, search };
}
