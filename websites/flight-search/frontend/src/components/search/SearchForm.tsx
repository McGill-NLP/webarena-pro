import { useState } from 'react';
import type { CabinClass, Passengers, TripType } from '../../api/types';
import { getMaxBookingDate, getMinBookingDate } from '../../utils/date';
import AirportInput from './AirportInput';
import ClassSelector from './ClassSelector';
import DatePicker from './DatePicker';
import PassengerSelector from './PassengerSelector';
import SwapButton from './SwapButton';
import TripTypeSelector from './TripTypeSelector';

export interface MultiCityLeg {
  origin: string;
  originDisplay: string;
  destination: string;
  destinationDisplay: string;
  date: string;
}

export interface SearchFormData {
  tripType: TripType;
  origin: string;
  originDisplay: string;
  destination: string;
  destinationDisplay: string;
  departureDate: string;
  returnDate: string;
  passengers: Passengers;
  cabinClass: CabinClass;
  multiCityLegs?: MultiCityLeg[];
}

interface Props {
  initial?: Partial<SearchFormData>;
  onSearch: (data: SearchFormData) => void;
  compact?: boolean;
}

const EMPTY_LEG: MultiCityLeg = { origin: '', originDisplay: '', destination: '', destinationDisplay: '', date: '' };

export default function SearchForm({ initial, onSearch, compact }: Props) {
  const [tripType, setTripType] = useState<TripType>(initial?.tripType || 'round_trip');
  const [origin, setOrigin] = useState(initial?.origin || '');
  const [originDisplay, setOriginDisplay] = useState(initial?.originDisplay || '');
  const [destination, setDestination] = useState(initial?.destination || '');
  const [destinationDisplay, setDestinationDisplay] = useState(initial?.destinationDisplay || '');
  const [departureDate, setDepartureDate] = useState(initial?.departureDate || '');
  const [returnDate, setReturnDate] = useState(initial?.returnDate || '');
  const minDate = getMinBookingDate();
  const maxDate = getMaxBookingDate();

  // Multi-city legs (2 legs by default, up to 3)
  const [mcLegs, setMcLegs] = useState<MultiCityLeg[]>(() => {
    if (initial?.multiCityLegs && initial.multiCityLegs.length >= 2) return initial.multiCityLegs;
    return [{ ...EMPTY_LEG }, { ...EMPTY_LEG }];
  });

  // Auto-adjust return date if it falls before departure date
  function handleDepartureDateChange(newDate: string) {
    setDepartureDate(newDate);
    if (returnDate && returnDate < newDate) {
      setReturnDate(newDate);
    }
  }
  const [passengers, setPassengers] = useState<Passengers>(initial?.passengers || { adults: 1, children: 0, infants: 0 });
  const [cabinClass, setCabinClass] = useState<CabinClass>(initial?.cabinClass || 'economy');

  function handleSwap() {
    const tmpCode = origin;
    const tmpDisplay = originDisplay;
    setOrigin(destination);
    setOriginDisplay(destinationDisplay);
    setDestination(tmpCode);
    setDestinationDisplay(tmpDisplay);
  }

  function updateMcLeg(index: number, updates: Partial<MultiCityLeg>) {
    setMcLegs(prev => {
      const next = [...prev];
      next[index] = { ...next[index], ...updates };
      // Auto-fill next leg's origin from this leg's destination
      if (updates.destination !== undefined && index < next.length - 1) {
        next[index + 1] = {
          ...next[index + 1],
          origin: updates.destination || '',
          originDisplay: updates.destinationDisplay || '',
        };
      }
      // Auto-adjust next leg dates to be >= this leg's date
      if (updates.date !== undefined) {
        for (let i = index + 1; i < next.length; i++) {
          if (next[i].date && next[i].date < next[i - 1].date) {
            next[i] = { ...next[i], date: next[i - 1].date };
          }
        }
      }
      return next;
    });
  }

  function addMcLeg() {
    if (mcLegs.length >= 3) return;
    const lastLeg = mcLegs[mcLegs.length - 1];
    setMcLegs(prev => [...prev, {
      ...EMPTY_LEG,
      origin: lastLeg.destination,
      originDisplay: lastLeg.destinationDisplay,
    }]);
  }

  function removeMcLeg(index: number) {
    if (mcLegs.length <= 2) return;
    setMcLegs(prev => {
      const next = prev.filter((_, i) => i !== index);
      // Re-chain: fix origin of leg after the removed one
      if (index > 0 && index < next.length) {
        next[index] = {
          ...next[index],
          origin: next[index - 1].destination,
          originDisplay: next[index - 1].destinationDisplay,
        };
      }
      return next;
    });
  }

  const isMultiCity = tripType === 'multi_city';
  const dateIsBeforeMin = (date: string) => Boolean(date && date < minDate);
  const dateIsAfterMax = (date: string) => Boolean(date && date > maxDate);
  const dateIsOutsideBookingWindow = (date: string) => dateIsBeforeMin(date) || dateIsAfterMax(date);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (isMultiCity) {
      // Validate all multi-city legs
      for (const leg of mcLegs) {
        if (!leg.origin || !leg.destination || !leg.date) return;
        if (dateIsOutsideBookingWindow(leg.date)) return;
      }
      onSearch({
        tripType,
        origin: mcLegs[0].origin,
        originDisplay: mcLegs[0].originDisplay,
        destination: mcLegs[mcLegs.length - 1].destination,
        destinationDisplay: mcLegs[mcLegs.length - 1].destinationDisplay,
        departureDate: mcLegs[0].date,
        returnDate: '',
        passengers,
        cabinClass,
        multiCityLegs: mcLegs,
      });
    } else {
      if (!origin || !destination || !departureDate) return;
      if (tripType === 'round_trip' && !returnDate) return;
      if (dateIsOutsideBookingWindow(departureDate)) return;
      if (returnDate && dateIsOutsideBookingWindow(returnDate)) return;
      onSearch({
        tripType, origin, originDisplay, destination, destinationDisplay,
        departureDate, returnDate, passengers, cabinClass,
      });
    }
  }

  const searchDisabled = isMultiCity
    ? mcLegs.some(l => !l.origin || !l.destination || !l.date || dateIsOutsideBookingWindow(l.date))
    : !origin || !destination || !departureDate || dateIsOutsideBookingWindow(departureDate)
      || (tripType === 'round_trip' && (!returnDate || dateIsOutsideBookingWindow(returnDate)));

  return (
    <form onSubmit={handleSubmit} data-testid="search-form">
      {/* Row 1: Trip type, passengers, class */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <TripTypeSelector value={tripType} onChange={setTripType} />
        <PassengerSelector value={passengers} onChange={setPassengers} />
        <ClassSelector value={cabinClass} onChange={setCabinClass} />
      </div>

      {isMultiCity ? (
        /* Multi-city: one row per leg */
        <div className={`space-y-2 ${compact ? '' : 'rounded-xl border border-gray-300 p-3'}`}>
          {mcLegs.map((leg, i) => (
            <div key={i} className="flex flex-wrap items-end gap-2" data-testid={`mc-leg-${i}`}>
              <div className="flex items-center mr-1">
                <span className="text-xs font-medium text-gray-500 bg-gray-100 rounded-full h-5 w-5 flex items-center justify-center">
                  {i + 1}
                </span>
              </div>
              <AirportInput
                label="From"
                value={leg.origin}
                displayValue={leg.originDisplay}
                onChange={(iata, display) => updateMcLeg(i, { origin: iata, originDisplay: display })}
                testId={`mc-origin-${i}`}
              />
              <AirportInput
                label="To"
                value={leg.destination}
                displayValue={leg.destinationDisplay}
                onChange={(iata, display) => updateMcLeg(i, { destination: iata, destinationDisplay: display })}
                testId={`mc-dest-${i}`}
              />
              <DatePicker
                label="Date"
                value={leg.date}
                onChange={(d) => updateMcLeg(i, { date: d })}
                min={i > 0 ? mcLegs[i - 1].date || minDate : minDate}
                max={maxDate}
                testId={`mc-date-${i}`}
              />
              {mcLegs.length > 2 && (
                <button
                  type="button"
                  onClick={() => removeMcLeg(i)}
                  className="rounded-full p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 cursor-pointer"
                  title="Remove flight"
                  data-testid={`mc-remove-${i}`}
                >
                  <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </button>
              )}
            </div>
          ))}
          <div className="flex items-center gap-2 pt-1">
            {mcLegs.length < 3 && (
              <button
                type="button"
                onClick={addMcLeg}
                className="flex items-center gap-1 rounded-full px-3 py-1.5 text-sm text-[#1a73e8] hover:bg-blue-50 cursor-pointer"
                data-testid="mc-add-leg"
              >
                <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
                </svg>
                Add flight
              </button>
            )}
            <div className="flex-1" />
            <button
              type="submit"
              disabled={searchDisabled}
              className="rounded-full bg-[#1a73e8] px-6 py-3 text-sm font-medium text-white hover:bg-[#1765cc] hover:shadow-md disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none cursor-pointer"
              data-testid="search-button"
            >
              Search
            </button>
          </div>
        </div>
      ) : (
        /* One-way / Round-trip: existing layout */
        <div className={`flex flex-wrap items-end gap-2 ${compact ? '' : 'rounded-xl border border-gray-300 p-3'}`}>
          <AirportInput
            label="Where from?"
            value={origin}
            displayValue={originDisplay}
            onChange={(iata, display) => { setOrigin(iata); setOriginDisplay(display); }}
            testId="origin"
          />

          <SwapButton onClick={handleSwap} />

          <AirportInput
            label="Where to?"
            value={destination}
            displayValue={destinationDisplay}
            onChange={(iata, display) => { setDestination(iata); setDestinationDisplay(display); }}
            testId="destination"
          />

          <DatePicker
            label="Departure"
            value={departureDate}
            onChange={handleDepartureDateChange}
            min={minDate}
            max={maxDate}
            testId="departure-date"
          />

          {tripType === 'round_trip' && (
            <DatePicker
              label="Return"
              value={returnDate}
              onChange={setReturnDate}
              min={departureDate || minDate}
              max={maxDate}
              testId="return-date"
            />
          )}

          <button
            type="submit"
            disabled={searchDisabled}
            className="rounded-full bg-[#1a73e8] px-6 py-3 text-sm font-medium text-white hover:bg-[#1765cc] hover:shadow-md disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none cursor-pointer"
            data-testid="search-button"
          >
            Search
          </button>
        </div>
      )}
    </form>
  );
}
