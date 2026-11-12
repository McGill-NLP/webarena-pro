import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { CabinClass, Filters, FlightOffer, Passengers, SearchLeg, SortBy, TripType } from '../api/types';
import { getLocalMinuteOfDay } from '../utils/format';
import { minRoundTripPrice, roundTripTotal, sharesAirline } from '../utils/pricing';
import SearchForm from '../components/search/SearchForm';
import type { MultiCityLeg, SearchFormData } from '../components/search/SearchForm';
import FlightCard from '../components/results/FlightCard';
import FilterPanel from '../components/results/FilterPanel';
import NoResults from '../components/results/NoResults';
import SelectedFlightBanner from '../components/results/SelectedFlightBanner';
import SortBar from '../components/results/SortBar';
import Loading from '../components/shared/Loading';
import { useFlightSearch } from '../hooks/useFlightSearch';
import { useCurrency } from '../contexts/CurrencyContext';

const EMPTY_FILTERS: Filters = {
  max_stops: null, max_price: null, max_duration_minutes: null,
  airlines: null, departure_time_min: null, departure_time_max: null,
};

// Parse multi-city legs from URL params
function parseMcLegs(searchParams: URLSearchParams): MultiCityLeg[] {
  const count = Number(searchParams.get('mcLegs') || 0);
  if (count < 2) return [];
  const legs: MultiCityLeg[] = [];
  for (let i = 0; i < count; i++) {
    legs.push({
      origin: searchParams.get(`mc${i}_origin`) || '',
      originDisplay: searchParams.get(`mc${i}_originDisplay`) || '',
      destination: searchParams.get(`mc${i}_dest`) || '',
      destinationDisplay: searchParams.get(`mc${i}_destDisplay`) || '',
      date: searchParams.get(`mc${i}_date`) || '',
    });
  }
  return legs;
}

export default function ResultsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { formatPrice, toUsd, symbol: currencySymbol } = useCurrency();
  const { outboundFlights, returnFlights, multiCityFlights, sameAirlineDiscount, loading, error, searched, search } = useFlightSearch();
  const [sortBy, setSortBy] = useState<SortBy>('best');
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [step, setStep] = useState<'outbound' | 'return'>('outbound');
  const [selectedOutbound, setSelectedOutbound] = useState<FlightOffer | null>(null);

  // Multi-city state
  const [mcStep, setMcStep] = useState(0); // which leg we're selecting
  const [mcSelected, setMcSelected] = useState<(FlightOffer | null)[]>([]);

  // Parse URL params
  const origin = searchParams.get('origin') || '';
  const destination = searchParams.get('destination') || '';
  const departureDate = searchParams.get('departure') || '';
  const returnDate = searchParams.get('return') || '';
  const tripType = (searchParams.get('tripType') || 'round_trip') as TripType;
  const cabinClass = (searchParams.get('cabinClass') || 'economy') as CabinClass;
  const passengers: Passengers = {
    adults: Number(searchParams.get('adults') || 1),
    children: Number(searchParams.get('children') || 0),
    infants: Number(searchParams.get('infants') || 0),
  };
  const originDisplay = searchParams.get('originDisplay') || origin;
  const destinationDisplay = searchParams.get('destinationDisplay') || destination;
  const mcLegsFromUrl = useMemo(() => parseMcLegs(searchParams), [searchParams]);

  const isMultiCity = tripType === 'multi_city' && multiCityFlights.length >= 2;
  const isRoundTrip = tripType === 'round_trip' && returnFlights.length > 0;
  const showingReturn = isRoundTrip && step === 'return' && selectedOutbound !== null;

  // Search on mount and param changes
  const doSearch = useCallback(() => {
    if (tripType === 'multi_city') {
      if (mcLegsFromUrl.length < 2) return;
      const apiLegs: SearchLeg[] = mcLegsFromUrl.map(l => ({ origin: l.origin, destination: l.destination, date: l.date }));
      search({
        tripType, origin, destination, departureDate,
        passengers, cabinClass, filters, sortBy,
        multiCityLegs: apiLegs,
      });
    } else {
      if (!origin || !destination || !departureDate) return;
      search({
        tripType, origin, destination, departureDate,
        returnDate: returnDate || undefined,
        passengers, cabinClass, filters, sortBy,
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- filters/sortBy intentionally excluded: filtering is client-side only
  }, [origin, destination, departureDate, returnDate, tripType, cabinClass,
      passengers.adults, passengers.children, passengers.infants,
      search, mcLegsFromUrl]);

  useEffect(() => { doSearch(); }, [doSearch]);

  // Reset multi-city selection state when search results change
  useEffect(() => {
    if (isMultiCity) {
      setMcStep(0);
      setMcSelected(multiCityFlights.map(() => null));
    }
  }, [multiCityFlights.length, isMultiCity]);

  // Memoized: minimum round-trip price for each outbound flight
  const outboundMinPrices = useMemo(() => {
    if (!isRoundTrip) return new Map<string, number>();
    const map = new Map<string, number>();
    for (const ob of outboundFlights) {
      const min = minRoundTripPrice(ob, returnFlights, sameAirlineDiscount);
      if (min !== null) map.set(ob.id, min);
    }
    return map;
  }, [outboundFlights, returnFlights, sameAirlineDiscount, isRoundTrip]);

  // Filter return flights: must depart at least 1 hour after outbound arrival
  const eligibleReturnFlights = useMemo(() => {
    if (!selectedOutbound) return returnFlights;
    const outboundArrival = new Date(selectedOutbound.arrival).getTime();
    const minDepartureTime = outboundArrival + 60 * 60 * 1000; // +1 hour
    return returnFlights.filter(f => new Date(f.departure).getTime() >= minDepartureTime);
  }, [returnFlights, selectedOutbound]);

  // Memoized: round-trip total for each return flight (given selected outbound)
  const returnRoundTripPrices = useMemo(() => {
    if (!selectedOutbound) return new Map<string, number>();
    const map = new Map<string, number>();
    for (const ret of eligibleReturnFlights) {
      map.set(ret.id, roundTripTotal(selectedOutbound, ret, sameAirlineDiscount));
    }
    return map;
  }, [eligibleReturnFlights, selectedOutbound, sameAirlineDiscount]);

  // Current flights to display (multi-city aware)
  const currentLegFlights = useMemo(() => {
    if (isMultiCity && multiCityFlights[mcStep]) {
      let flights = multiCityFlights[mcStep];
      // For legs after the first, filter: depart >= 1h after previous leg arrival
      if (mcStep > 0 && mcSelected[mcStep - 1]) {
        const prevArrival = new Date(mcSelected[mcStep - 1]!.arrival).getTime();
        const minDep = prevArrival + 60 * 60 * 1000;
        flights = flights.filter(f => new Date(f.departure).getTime() >= minDep);
      }
      return flights;
    }
    return [];
  }, [isMultiCity, multiCityFlights, mcStep, mcSelected]);

  // Client-side filter + sort the results
  const filteredFlights = useMemo(() => {
    let flights: FlightOffer[];
    if (isMultiCity) {
      flights = currentLegFlights;
    } else {
      flights = showingReturn ? eligibleReturnFlights : outboundFlights;
    }

    if (filters.max_stops !== null && filters.max_stops !== undefined) {
      flights = flights.filter(f => f.stops <= filters.max_stops!);
    }
    if (filters.max_price) {
      // Convert display-currency amount to USD for comparison against price_usd
      const maxUsd = toUsd(filters.max_price);
      flights = flights.filter(f => {
        // For round trips, filter by the round-trip price shown to the user
        if (showingReturn && selectedOutbound) {
          return (returnRoundTripPrices.get(f.id) ?? f.price_usd) <= maxUsd;
        }
        if (isRoundTrip && !showingReturn) {
          return (outboundMinPrices.get(f.id) ?? f.price_usd) <= maxUsd;
        }
        return f.price_usd <= maxUsd;
      });
    }
    if (filters.airlines && filters.airlines.length > 0) {
      const set = new Set(filters.airlines);
      flights = flights.filter(f => f.segments.some(s => set.has(s.airline_code)));
    }
    if (filters.departure_time_min) {
      const [h, m] = filters.departure_time_min.split(':').map(Number);
      const min = h * 60 + m;
      flights = flights.filter(f => getLocalMinuteOfDay(f.departure) >= min);
    }
    if (filters.departure_time_max) {
      const [h, m] = filters.departure_time_max.split(':').map(Number);
      const max = h * 60 + m;
      flights = flights.filter(f => getLocalMinuteOfDay(f.departure) <= max);
    }

    // Sort
    if (sortBy === 'cheapest') {
      if (showingReturn && selectedOutbound) {
        flights = [...flights].sort((a, b) =>
          (returnRoundTripPrices.get(a.id) ?? a.price_usd) - (returnRoundTripPrices.get(b.id) ?? b.price_usd)
        );
      } else if (isRoundTrip && !showingReturn) {
        flights = [...flights].sort((a, b) =>
          (outboundMinPrices.get(a.id) ?? a.price_usd) - (outboundMinPrices.get(b.id) ?? b.price_usd)
        );
      } else {
        flights = [...flights].sort((a, b) => a.price_usd - b.price_usd);
      }
    } else if (sortBy === 'fastest') {
      flights = [...flights].sort((a, b) => a.total_duration_minutes - b.total_duration_minutes);
    } else {
      const maxP = Math.max(...flights.map(f => f.price_usd), 1);
      const maxD = Math.max(...flights.map(f => f.total_duration_minutes), 1);
      flights = [...flights].sort((a, b) =>
        (a.price_usd / maxP * 0.6 + a.total_duration_minutes / maxD * 0.4)
        - (b.price_usd / maxP * 0.6 + b.total_duration_minutes / maxD * 0.4)
      );
    }

    return flights;
  }, [outboundFlights, eligibleReturnFlights, currentLegFlights, showingReturn, isRoundTrip, isMultiCity, selectedOutbound, outboundMinPrices, returnRoundTripPrices, filters, sortBy, toUsd]);

  // Split into "best" and "other" flights
  const bestFlights = useMemo(() => filteredFlights.filter(f => f.is_best), [filteredFlights]);
  const otherFlights = useMemo(() => filteredFlights.filter(f => !f.is_best), [filteredFlights]);

  const hasFilters = filters.max_stops !== null || !!filters.max_price || !!filters.airlines
    || !!filters.departure_time_min || !!filters.departure_time_max;

  function handleNewSearch(data: SearchFormData) {
    const params = new URLSearchParams({
      origin: data.origin,
      destination: data.destination,
      departure: data.departureDate,
      tripType: data.tripType,
      cabinClass: data.cabinClass,
      adults: String(data.passengers.adults),
      children: String(data.passengers.children),
      infants: String(data.passengers.infants),
      originDisplay: data.originDisplay,
      destinationDisplay: data.destinationDisplay,
    });
    if (data.tripType === 'round_trip') {
      params.set('return', data.returnDate);
    }
    if (data.tripType === 'multi_city' && data.multiCityLegs) {
      params.set('mcLegs', String(data.multiCityLegs.length));
      data.multiCityLegs.forEach((leg, i) => {
        params.set(`mc${i}_origin`, leg.origin);
        params.set(`mc${i}_dest`, leg.destination);
        params.set(`mc${i}_date`, leg.date);
        params.set(`mc${i}_originDisplay`, leg.originDisplay);
        params.set(`mc${i}_destDisplay`, leg.destinationDisplay);
      });
    }
    setSearchParams(params);
    setFilters(EMPTY_FILTERS);
    setSortBy('best');
    setStep('outbound');
    setSelectedOutbound(null);
    setMcStep(0);
    setMcSelected([]);
  }

  function handleSelectOutbound(flight: FlightOffer) {
    setSelectedOutbound(flight);
    setStep('return');
  }

  function handleChangeOutbound() {
    setStep('outbound');
    setSelectedOutbound(null);
    setFilters(EMPTY_FILTERS);
    setSortBy('best');
  }

  function handleBookOneWay(flight: FlightOffer) {
    navigate('/booking-options', { state: { outboundFlight: flight } });
  }

  function handleBookReturn(returnFlight: FlightOffer) {
    const basePrice = selectedOutbound
      ? roundTripTotal(selectedOutbound, returnFlight, sameAirlineDiscount)
      : undefined;
    navigate('/booking-options', { state: { outboundFlight: selectedOutbound, returnFlight, basePrice } });
  }

  // Multi-city handlers
  function handleSelectMcFlight(flight: FlightOffer) {
    setMcSelected(prev => {
      const next = [...prev];
      next[mcStep] = flight;
      return next;
    });
    if (mcStep < multiCityFlights.length - 1) {
      setMcStep(mcStep + 1);
      setFilters(EMPTY_FILTERS);
      setSortBy('best');
    }
  }

  function handleGoToMcStep(stepIdx: number) {
    // Can only go back to already-selected steps or current step
    if (stepIdx <= mcStep) {
      setMcStep(stepIdx);
      // Clear selections from this step onward
      setMcSelected(prev => {
        const next = [...prev];
        for (let i = stepIdx; i < next.length; i++) next[i] = null;
        return next;
      });
      setFilters(EMPTY_FILTERS);
      setSortBy('best');
    }
  }

  function handleBookMultiCity() {
    const selectedFlights = mcSelected.filter(Boolean) as FlightOffer[];
    if (selectedFlights.length !== multiCityFlights.length) return;
    navigate('/booking-options', {
      state: {
        outboundFlight: selectedFlights[0],
        multiCityFlights: selectedFlights,
      },
    });
  }

  // Is multi-city fully selected?
  const mcFullySelected = isMultiCity && mcSelected.length === multiCityFlights.length && mcSelected.every(Boolean);

  // Section heading
  function getSectionHeading(isBest: boolean): string {
    if (isMultiCity) {
      const leg = mcLegsFromUrl[mcStep];
      const label = leg ? `${leg.originDisplay || leg.origin} to ${leg.destinationDisplay || leg.destination}` : `Flight ${mcStep + 1}`;
      return isBest ? `Best flights: ${label}` : `Other flights: ${label}`;
    }
    if (showingReturn) return isBest ? 'Best returning flights' : 'Other returning flights';
    return isBest ? 'Best departing flights' : 'Other departing flights';
  }

  // Flights to use for the filter panel
  const filterSourceFlights = isMultiCity ? currentLegFlights : (showingReturn ? eligibleReturnFlights : outboundFlights);
  const hasResults = isMultiCity ? multiCityFlights.some(l => l.length > 0) : outboundFlights.length > 0;

  return (
    <div className="min-h-screen bg-gray-50" data-testid="results-page">
      {/* Collapsed search form */}
      <div className="border-b border-gray-200 bg-white shadow-sm">
        <div className="mx-auto max-w-6xl px-4 py-4">
          <SearchForm
            compact
            initial={{
              tripType, origin, originDisplay, destination, destinationDisplay,
              departureDate, returnDate, passengers, cabinClass,
              multiCityLegs: mcLegsFromUrl.length >= 2 ? mcLegsFromUrl : undefined,
            }}
            onSearch={handleNewSearch}
          />
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-4 py-6">
        {/* Step breadcrumb for round trip */}
        {isRoundTrip && searched && (
          <div className="mb-4 flex items-center gap-2 text-sm" data-testid="step-breadcrumb">
            <button
              onClick={handleChangeOutbound}
              className={`font-medium cursor-pointer ${step === 'outbound' ? 'text-[#1a73e8]' : 'text-gray-500 hover:text-gray-700'}`}
              data-testid="breadcrumb-outbound"
            >
              1. Select departing flight
            </button>
            <svg className="h-4 w-4 text-gray-400" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd"/>
            </svg>
            <span className={`font-medium ${step === 'return' ? 'text-[#1a73e8]' : 'text-gray-400'}`}>
              2. Select return flight
            </span>
          </div>
        )}

        {/* Step breadcrumb for multi-city */}
        {isMultiCity && searched && (
          <div className="mb-4 flex items-center gap-2 text-sm flex-wrap" data-testid="mc-step-breadcrumb">
            {multiCityFlights.map((_, i) => {
              const leg = mcLegsFromUrl[i];
              const label = leg ? `${leg.originDisplay || leg.origin} \u2192 ${leg.destinationDisplay || leg.destination}` : `Flight ${i + 1}`;
              return (
                <span key={i} className="flex items-center gap-2">
                  {i > 0 && (
                    <svg className="h-4 w-4 text-gray-400" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd"/>
                    </svg>
                  )}
                  <button
                    onClick={() => handleGoToMcStep(i)}
                    disabled={i > mcStep}
                    className={`font-medium cursor-pointer disabled:cursor-default ${
                      i === mcStep ? 'text-[#1a73e8]' :
                      i < mcStep ? 'text-gray-500 hover:text-gray-700' :
                      'text-gray-400'
                    }`}
                    data-testid={`mc-breadcrumb-${i}`}
                  >
                    {i + 1}. {label}
                    {mcSelected[i] && i < mcStep && ' \u2713'}
                  </button>
                </span>
              );
            })}
          </div>
        )}

        {/* Selected flight banners for multi-city */}
        {isMultiCity && mcStep > 0 && mcSelected.slice(0, mcStep).map((flight, i) => (
          flight && (
            <div key={i} className="mb-2">
              <SelectedFlightBanner
                flight={flight}
                onChangeClick={() => handleGoToMcStep(i)}
                label={`Flight ${i + 1}`}
              />
            </div>
          )
        ))}

        {/* Selected outbound banner on return step (round-trip) */}
        {showingReturn && selectedOutbound && (
          <SelectedFlightBanner flight={selectedOutbound} onChangeClick={handleChangeOutbound} />
        )}

        {/* Multi-city: all selected -> show summary & book button */}
        {mcFullySelected && (
          <div className="mb-6 rounded-lg border border-gray-200 bg-white p-5 shadow-sm" data-testid="mc-summary">
            <h2 className="text-lg font-medium text-gray-900 mb-3">Your multi-city trip</h2>
            {(mcSelected as FlightOffer[]).map((flight, i) => {
              const leg = mcLegsFromUrl[i];
              return (
                <div key={i} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900">
                      Flight {i + 1}: {leg?.originDisplay || flight.origin} &rarr; {leg?.destinationDisplay || flight.destination}
                    </div>
                    <div className="text-xs text-gray-500">
                      {flight.segments[0].airline_name} &middot; {flight.stops === 0 ? 'Nonstop' : `${flight.stops} stop${flight.stops > 1 ? 's' : ''}`}
                    </div>
                  </div>
                  <div className="text-sm font-medium text-gray-900 ml-4">
                    {formatPrice(flight.price_usd)}
                  </div>
                  <button
                    onClick={() => handleGoToMcStep(i)}
                    className="ml-3 text-xs text-[#1a73e8] hover:underline cursor-pointer"
                  >
                    Change
                  </button>
                </div>
              );
            })}
            <div className="mt-3 flex items-center justify-end">
              <button
                onClick={handleBookMultiCity}
                className="rounded-full bg-[#1a73e8] px-6 py-2.5 text-sm font-medium text-white hover:bg-[#1557b0] cursor-pointer"
                data-testid="mc-book-button"
              >
                Continue to booking
              </button>
            </div>
          </div>
        )}

        <div className="flex gap-6">
          {/* Filters sidebar */}
          {searched && hasResults && !mcFullySelected && (
            <aside className="hidden lg:block w-64 flex-shrink-0">
              <div className="sticky top-4 rounded-lg bg-white p-4 shadow-sm">
                <FilterPanel
                  flights={filterSourceFlights}
                  filters={filters}
                  onChange={setFilters}
                  currencySymbol={currencySymbol}
                />
              </div>
            </aside>
          )}

          {/* Main content */}
          <main className="flex-1 min-w-0">
            {loading && <Loading />}

            {error && (
              <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700" data-testid="error-message">
                {error}
              </div>
            )}

            {searched && !loading && !error && !mcFullySelected && (
              <>
                <div className="mb-4">
                  <SortBar value={sortBy} onChange={setSortBy} resultCount={filteredFlights.length} />
                </div>

                {filteredFlights.length === 0 ? (
                  <NoResults hasFilters={hasFilters} onClearFilters={() => setFilters(EMPTY_FILTERS)} />
                ) : (
                  <div>
                    {/* Best flights section */}
                    {bestFlights.length > 0 && (
                      <section className="mb-6" data-testid="best-flights-section">
                        <div className="mb-2 flex items-center gap-2">
                          <h2 className="text-sm font-medium text-gray-900">
                            {getSectionHeading(true)}
                          </h2>
                          <div className="group relative">
                            <svg className="h-4 w-4 text-gray-400 cursor-help" viewBox="0 0 20 20" fill="currentColor">
                              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clipRule="evenodd"/>
                            </svg>
                            <div className="hidden group-hover:block absolute left-0 top-6 z-50 w-64 rounded-lg bg-gray-800 p-3 text-xs text-white shadow-lg">
                              Ranked based on price and convenience factors including duration, number of stops, and layover airports.
                            </div>
                          </div>
                        </div>
                        <div className="space-y-2" data-testid="best-flights-list">
                          {bestFlights.map(flight => (
                            <FlightCard
                              key={flight.id}
                              flight={flight}
                              roundTripPrice={showingReturn
                                ? returnRoundTripPrices.get(flight.id)
                                : isRoundTrip ? outboundMinPrices.get(flight.id) : undefined}
                              priceLabel={showingReturn ? 'round trip' : isRoundTrip ? 'from, round trip' : undefined}
                              onSelect={isMultiCity ? handleSelectMcFlight : (isRoundTrip && !showingReturn ? handleSelectOutbound : undefined)}
                              onBook={!isRoundTrip && !isMultiCity ? handleBookOneWay : showingReturn ? handleBookReturn : undefined}
                              discountApplied={showingReturn && selectedOutbound ? sharesAirline(flight, selectedOutbound) : false}
                            />
                          ))}
                        </div>
                      </section>
                    )}

                    {/* Other flights section */}
                    {otherFlights.length > 0 && (
                      <section data-testid="other-flights-section">
                        {bestFlights.length > 0 && (
                          <div className="mb-2 mt-2 flex items-center gap-3">
                            <div className="h-px flex-1 bg-gray-200" />
                            <h2 className="text-sm font-medium text-gray-500 whitespace-nowrap">
                              {getSectionHeading(false)}
                            </h2>
                            <div className="h-px flex-1 bg-gray-200" />
                          </div>
                        )}
                        <div className="space-y-2" data-testid="other-flights-list">
                          {otherFlights.map(flight => (
                            <FlightCard
                              key={flight.id}
                              flight={flight}
                              roundTripPrice={showingReturn
                                ? returnRoundTripPrices.get(flight.id)
                                : isRoundTrip ? outboundMinPrices.get(flight.id) : undefined}
                              priceLabel={showingReturn ? 'round trip' : isRoundTrip ? 'from, round trip' : undefined}
                              onSelect={isMultiCity ? handleSelectMcFlight : (isRoundTrip && !showingReturn ? handleSelectOutbound : undefined)}
                              onBook={!isRoundTrip && !isMultiCity ? handleBookOneWay : showingReturn ? handleBookReturn : undefined}
                              discountApplied={showingReturn && selectedOutbound ? sharesAirline(flight, selectedOutbound) : false}
                            />
                          ))}
                        </div>
                      </section>
                    )}
                  </div>
                )}
              </>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
