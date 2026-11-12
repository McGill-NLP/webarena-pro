import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getCheapFlights, getPopularDestinations, searchAirports } from '../api/client';
import type { AutocompleteResult, DestinationCard, GeolocationResponse } from '../api/types';
import SearchForm from '../components/search/SearchForm';
import type { SearchFormData } from '../components/search/SearchForm';
import { useCurrency } from '../contexts/CurrencyContext';
import { useDebounce } from '../hooks/useDebounce';

interface Props {
  geo?: GeolocationResponse | null;
}

const FAQ_ITEMS = [
  {
    q: 'How do I find the cheapest flights?',
    a: 'Use flexible dates and search for flights midweek (Tuesday or Wednesday) for the best deals. Booking 3-8 weeks in advance typically offers the lowest fares for domestic flights, while international flights are cheapest 2-3 months ahead.',
  },
  {
    q: 'Can I change or cancel my flight after booking?',
    a: 'It depends on your fare type. Flex fares include free changes and cancellations, while Basic Economy fares may have restrictions. Check your booking options when selecting a fare to see what\'s included.',
  },
  {
    q: 'What currency are prices displayed in?',
    a: 'Prices default to your local currency based on your location. You can change the currency at any time using the currency selector in the top-right corner of the page. All prices are converted from USD using current exchange rates.',
  },
  {
    q: 'How far in advance can I book a flight?',
    a: 'You can search for and book flights up to 12 months in advance. Prices are typically lowest when booking 6-8 weeks before departure for domestic flights and 2-3 months for international routes.',
  },
  {
    q: 'Are the prices shown per person or total?',
    a: 'All prices displayed in search results are per person for a one-way trip. For round trips, the total price includes both outbound and return flights. Additional fees for baggage, seat selection, or upgrades may apply depending on your fare type.',
  },
  {
    q: 'What does "Best" flight mean?',
    a: 'Flights tagged as "Best" are scored using a combination of price (45%), duration (35%), and number of stops (20%). This helps you find flights that balance cost and convenience rather than just the cheapest option.',
  },
];

export default function SearchPage({ geo }: Props) {
  const navigate = useNavigate();
  const { formatPrice } = useCurrency();
  const [popular, setPopular] = useState<DestinationCard[]>([]);
  const [cheap, setCheap] = useState<DestinationCard[]>([]);
  const [cheapTab, setCheapTab] = useState<'popular' | 'domestic' | 'international'>('popular');
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null);

  // Dynamic origin state
  const [originIata, setOriginIata] = useState('');
  const [originCity, setOriginCity] = useState('');
  const [originDisplay, setOriginDisplay] = useState('');

  // Origin search
  const [originQuery, setOriginQuery] = useState('');
  const [originResults, setOriginResults] = useState<AutocompleteResult[]>([]);
  const [originDropdownOpen, setOriginDropdownOpen] = useState(false);
  const [originFocused, setOriginFocused] = useState(false);
  const debouncedOriginQuery = useDebounce(originQuery, 200);
  const originRef = useRef<HTMLDivElement>(null);

  // Set initial origin from geolocation
  useEffect(() => {
    if (geo?.nearest_airports?.[0] && !originIata) {
      const airport = geo.nearest_airports[0];
      setOriginIata(airport.iata);
      setOriginCity(geo.city || airport.city);
      setOriginDisplay(`${geo.city || airport.city} (${airport.iata})`);
      setOriginQuery(`${geo.city || airport.city} (${airport.iata})`);
    }
  }, [geo, originIata]);

  // Fetch origin autocomplete
  useEffect(() => {
    if (!originFocused || debouncedOriginQuery.length < 1) {
      setOriginResults([]);
      return;
    }
    let cancelled = false;
    searchAirports(debouncedOriginQuery).then(r => {
      if (!cancelled) {
        setOriginResults(r);
        setOriginDropdownOpen(r.length > 0);
      }
    });
    return () => { cancelled = true; };
  }, [debouncedOriginQuery, originFocused]);

  // Close dropdown on click outside
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (originRef.current && !originRef.current.contains(e.target as Node)) {
        setOriginDropdownOpen(false);
        setOriginFocused(false);
        if (originIata) setOriginQuery(originDisplay);
        else setOriginQuery('');
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [originIata, originDisplay]);

  function selectOrigin(r: AutocompleteResult) {
    setOriginIata(r.iata);
    setOriginCity(r.city_name);
    const display = `${r.city_name} (${r.iata})`;
    setOriginDisplay(display);
    setOriginQuery(display);
    setOriginDropdownOpen(false);
    setOriginFocused(false);
  }

  // Fetch popular destinations when origin changes
  useEffect(() => {
    if (!originIata) return;
    getPopularDestinations(originIata, 8).then((r) => setPopular(r.destinations)).catch(() => {});
  }, [originIata]);

  // Fetch cheap flights when origin or tab changes
  useEffect(() => {
    if (!originIata) return;
    getCheapFlights(originIata, cheapTab, 8).then((r) => setCheap(r.flights)).catch(() => {});
  }, [originIata, cheapTab]);

  function handleSearch(data: SearchFormData) {
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
    navigate(`/results?${params.toString()}`);
  }

  function handleDestinationClick(dest: DestinationCard) {
    if (!originIata) return;
    const params = new URLSearchParams({
      origin: originIata,
      destination: dest.iata,
      departure: dest.cheapest_date,
      originDisplay: originDisplay || `${originCity} (${originIata})`,
      destinationDisplay: `${dest.city} (${dest.iata})`,
      tripType: 'one_way',
      cabinClass: 'economy',
      adults: '1',
      children: '0',
      infants: '0',
    });
    navigate(`/results?${params.toString()}`);
  }

  return (
    <div className="min-h-screen bg-white" data-testid="search-page">
      {/* Hero Section */}
      <div className="relative overflow-hidden bg-gradient-to-br from-[#1a73e8] via-[#4285f4] to-[#669df6]">
        {/* Sky pattern overlay */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-10 left-[10%] h-32 w-64 rounded-full bg-white blur-3xl" />
          <div className="absolute top-20 right-[15%] h-24 w-48 rounded-full bg-white blur-3xl" />
          <div className="absolute bottom-10 left-[30%] h-20 w-40 rounded-full bg-white blur-3xl" />
        </div>

        <div className="relative mx-auto max-w-4xl px-4 pt-16 pb-28">
          <div className="text-center mb-8">
            <h1 className="text-5xl font-normal text-white mb-3" data-testid="hero-title">
              Flights
            </h1>
            <p className="text-lg text-blue-100">
              Explore the world and find your next adventure
            </p>
          </div>
        </div>
      </div>

      {/* Search Form — overlapping hero */}
      <div className="mx-auto max-w-4xl px-4 -mt-16 relative z-10 mb-12">
        <div className="rounded-2xl bg-white p-6 shadow-xl border border-gray-100">
          <SearchForm onSearch={handleSearch} />
        </div>
      </div>

      {/* Origin selector for destinations */}
      {originIata && (
        <div className="mx-auto max-w-4xl px-4 mb-2">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <svg className="h-4 w-4 text-gray-400 flex-shrink-0" viewBox="0 0 24 24" fill="none">
              <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" fill="currentColor"/>
            </svg>
            <span>Showing flights from</span>
            <div ref={originRef} className="relative inline-block">
              <button
                onClick={() => { setOriginFocused(true); setOriginQuery(''); setOriginDropdownOpen(true); }}
                className="text-[#1a73e8] font-medium hover:underline cursor-pointer"
              >
                {originDisplay || 'Select city'}
              </button>
              {originFocused && (
                <div className="absolute top-full left-0 z-50 mt-1 w-72">
                  <input
                    type="text"
                    value={originQuery}
                    onChange={e => { setOriginQuery(e.target.value); setOriginDropdownOpen(true); }}
                    placeholder="Search city or airport"
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-lg focus:border-[#1a73e8] focus:outline-none"
                    autoFocus
                  />
                  {originDropdownOpen && originResults.length > 0 && (
                    <ul className="mt-1 max-h-52 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg">
                      {originResults.map(r => (
                        <li
                          key={r.iata}
                          onClick={() => selectOrigin(r)}
                          className="flex cursor-pointer items-center gap-3 px-3 py-2.5 hover:bg-gray-50 text-sm"
                        >
                          <span className="font-medium text-gray-900">{r.city_name} ({r.iata})</span>
                          <span className="text-xs text-gray-400 truncate">{r.country}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Popular Destinations */}
      {popular.length > 0 && (
        <section className="mx-auto max-w-4xl px-4 mb-12 mt-4">
          <h2 className="text-2xl font-normal text-gray-900 mb-1">
            Popular destinations
          </h2>
          <p className="text-sm text-gray-500 mb-5">
            Lowest fares in the next 3 months
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {popular.slice(0, 8).map((dest) => (
              <button
                key={dest.iata}
                onClick={() => handleDestinationClick(dest)}
                className="group rounded-2xl border border-gray-200 bg-white overflow-hidden text-left hover:shadow-lg transition-shadow cursor-pointer"
              >
                {/* Gradient placeholder for city image */}
                <div className="h-32 relative overflow-hidden">
                  <div className={`absolute inset-0 ${getGradient(dest.iata)}`} />
                  <div className="absolute bottom-2 left-3 text-white">
                    <div className="text-lg font-medium drop-shadow-md">{dest.city}</div>
                    <div className="text-xs text-white/80 drop-shadow-md">{dest.country}</div>
                  </div>
                </div>
                <div className="px-3 py-3 flex items-center justify-between">
                  <div className="text-xs text-gray-500">{dest.iata}</div>
                  <div className="text-sm font-medium text-gray-900">
                    {formatPrice(dest.price_usd)}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Cheap Flights */}
      {originIata && (
        <section className="mx-auto max-w-4xl px-4 mb-12">
          <h2 className="text-2xl font-normal text-gray-900 mb-1">
            Cheap flights
          </h2>
          <p className="text-sm text-gray-500 mb-4">
            The lowest fares in the next 3 months
          </p>

          {/* Tabs */}
          <div className="flex gap-2 mb-5">
            {(['popular', 'domestic', 'international'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setCheapTab(tab)}
                className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors cursor-pointer ${
                  cheapTab === tab
                    ? 'bg-[#1a73e8] text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>

          {cheap.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {cheap.slice(0, 8).map((dest) => (
                <button
                  key={dest.iata}
                  onClick={() => handleDestinationClick(dest)}
                  className="rounded-xl border border-gray-200 bg-white px-4 py-3 text-left hover:shadow-md transition-shadow cursor-pointer"
                >
                  <div className="text-sm font-medium text-gray-900">{dest.city}</div>
                  <div className="flex items-center justify-between mt-0.5">
                    <span className="text-xs text-gray-500">{dest.country}</span>
                    <span className="text-sm font-medium text-[#1a73e8]">{formatPrice(dest.price_usd)}</span>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 py-4">No flights found for this category.</p>
          )}
        </section>
      )}

      {/* FAQ Section */}
      <section className="mx-auto max-w-4xl px-4 mb-16">
        <h2 className="text-2xl font-normal text-gray-900 mb-5">
          Frequently asked questions
        </h2>
        <div className="divide-y divide-gray-200 border-t border-b border-gray-200">
          {FAQ_ITEMS.map((item, i) => (
            <div key={i}>
              <button
                onClick={() => setExpandedFaq(expandedFaq === i ? null : i)}
                className="flex w-full items-center justify-between py-4 text-left cursor-pointer"
              >
                <span className="text-sm font-medium text-gray-900 pr-4">{item.q}</span>
                <svg
                  className={`h-5 w-5 text-gray-400 flex-shrink-0 transition-transform ${
                    expandedFaq === i ? 'rotate-180' : ''
                  }`}
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
              {expandedFaq === i && (
                <div className="pb-4 text-sm text-gray-600 leading-relaxed">
                  {item.a}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

// Deterministic gradient based on airport code
function getGradient(iata: string): string {
  const gradients = [
    'bg-gradient-to-br from-blue-500 to-purple-600',
    'bg-gradient-to-br from-emerald-500 to-teal-600',
    'bg-gradient-to-br from-orange-400 to-rose-500',
    'bg-gradient-to-br from-indigo-500 to-blue-600',
    'bg-gradient-to-br from-pink-500 to-purple-600',
    'bg-gradient-to-br from-cyan-500 to-blue-500',
    'bg-gradient-to-br from-amber-400 to-orange-500',
    'bg-gradient-to-br from-violet-500 to-indigo-600',
  ];
  const hash = iata.charCodeAt(0) + iata.charCodeAt(1) + iata.charCodeAt(2);
  return gradients[hash % gradients.length];
}

