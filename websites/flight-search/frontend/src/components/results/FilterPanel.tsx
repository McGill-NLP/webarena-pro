import { useMemo } from 'react';
import type { Filters, FlightOffer } from '../../api/types';

interface Props {
  flights: FlightOffer[];
  filters: Filters;
  onChange: (f: Filters) => void;
  currencySymbol?: string;
}

export default function FilterPanel({ flights, filters, onChange, currencySymbol = '$' }: Props) {
  // Compute available filter options from flights
  const airlines = useMemo(() => {
    const map = new Map<string, string>();
    flights.forEach(f => f.segments.forEach(s => map.set(s.airline_code, s.airline_name)));
    return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [flights]);

  return (
    <div className="space-y-6" data-testid="filter-panel">
      {/* Stops filter */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-gray-900">Stops</h3>
        <div className="space-y-1">
          {[null, 0, 1, 2].map(v => (
            <label key={String(v)} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="stops"
                checked={filters.max_stops === v}
                onChange={() => onChange({ ...filters, max_stops: v })}
                className="accent-[#1a73e8]"
                data-testid={`filter-stops-${v === null ? 'any' : v}`}
              />
              <span className="text-sm text-gray-700">
                {v === null ? 'Any' : v === 0 ? 'Nonstop only' : `Up to ${v} stop${v > 1 ? 's' : ''}`}
              </span>
            </label>
          ))}
        </div>
      </div>

      {/* Price filter */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-gray-900">Max price</h3>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">{currencySymbol}</span>
          <input
            type="number"
            value={filters.max_price ?? ''}
            onChange={e => onChange({ ...filters, max_price: e.target.value ? Number(e.target.value) : null })}
            placeholder="Any"
            className="w-24 rounded border border-gray-300 px-2 py-1 text-sm focus:border-[#1a73e8] focus:outline-none"
            min={0}
            data-testid="filter-max-price"
          />
        </div>
      </div>

      {/* Departure time filter */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-gray-900">Departure time</h3>
        <div className="flex items-center gap-2">
          <input
            type="time"
            value={filters.departure_time_min ?? ''}
            onChange={e => onChange({ ...filters, departure_time_min: e.target.value || null })}
            className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-[#1a73e8] focus:outline-none"
            data-testid="filter-dep-time-min"
          />
          <span className="text-xs text-gray-500">to</span>
          <input
            type="time"
            value={filters.departure_time_max ?? ''}
            onChange={e => onChange({ ...filters, departure_time_max: e.target.value || null })}
            className="rounded border border-gray-300 px-2 py-1 text-sm focus:border-[#1a73e8] focus:outline-none"
            data-testid="filter-dep-time-max"
          />
        </div>
      </div>

      {/* Airlines filter */}
      {airlines.length > 1 && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-gray-900">Airlines</h3>
          <div className="max-h-48 space-y-1 overflow-y-auto">
            {airlines.map(([code, name]) => {
              const selected = !filters.airlines || filters.airlines.includes(code);
              return (
                <label key={code} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={() => {
                      let next: string[] | null;
                      if (!filters.airlines) {
                        // First deselection: select all except this one
                        next = airlines.filter(([c]) => c !== code).map(([c]) => c);
                      } else if (selected) {
                        next = filters.airlines.filter(c => c !== code);
                        if (next.length === 0) next = null; // deselect all = any
                      } else {
                        next = [...filters.airlines, code];
                        if (next.length === airlines.length) next = null; // all selected = any
                      }
                      onChange({ ...filters, airlines: next });
                    }}
                    className="accent-[#1a73e8]"
                    data-testid={`filter-airline-${code}`}
                  />
                  <span className="text-sm text-gray-700">{name} ({code})</span>
                </label>
              );
            })}
          </div>
        </div>
      )}

      {/* Clear all */}
      <button
        onClick={() => onChange({
          max_stops: null, max_price: null, max_duration_minutes: null,
          airlines: null, departure_time_min: null, departure_time_max: null,
        })}
        className="text-sm text-[#1a73e8] hover:underline cursor-pointer"
        data-testid="filter-clear"
      >
        Clear all filters
      </button>
    </div>
  );
}
