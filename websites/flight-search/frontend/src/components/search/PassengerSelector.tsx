import { useEffect, useRef, useState } from 'react';
import type { Passengers } from '../../api/types';

interface Props {
  value: Passengers;
  onChange: (v: Passengers) => void;
}

export default function PassengerSelector({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const total = value.adults + value.children + value.infants;

  function update(field: keyof Passengers, delta: number) {
    const v = { ...value };
    v[field] = Math.max(field === 'adults' ? 1 : 0, Math.min(9, v[field] + delta));
    onChange(v);
  }

  return (
    <div ref={ref} className="relative" data-testid="passenger-selector">
      <button
        onClick={() => setOpen(!open)}
        className="rounded-md border border-gray-300 px-3 py-3 text-sm text-gray-700 hover:border-gray-400 focus:border-[#1a73e8] focus:outline-none flex items-center gap-1 cursor-pointer"
        aria-label="Passengers"
        data-testid="passenger-button"
      >
        <svg className="h-4 w-4 text-gray-500" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
        </svg>
        <span>{total}</span>
        <svg className="h-4 w-4 text-gray-400" viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd"/>
        </svg>
      </button>

      {open && (
        <div className="absolute top-full right-0 z-50 mt-1 w-64 rounded-lg border border-gray-200 bg-white p-4 shadow-lg" data-testid="passenger-dropdown">
          {([
            { key: 'adults' as const, label: 'Adults', sub: '' },
            { key: 'children' as const, label: 'Children', sub: 'Aged 2-11' },
            { key: 'infants' as const, label: 'Infants', sub: 'Under 2' },
          ]).map(row => (
            <div key={row.key} className="flex items-center justify-between py-2">
              <div>
                <div className="text-sm font-medium text-gray-900">{row.label}</div>
                {row.sub && <div className="text-xs text-gray-500">{row.sub}</div>}
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => update(row.key, -1)}
                  disabled={value[row.key] <= (row.key === 'adults' ? 1 : 0)}
                  className="h-8 w-8 rounded-full border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center"
                  aria-label={`Decrease ${row.label}`}
                  data-testid={`${row.key}-decrease`}
                >−</button>
                <span className="w-4 text-center text-sm" data-testid={`${row.key}-count`}>{value[row.key]}</span>
                <button
                  onClick={() => update(row.key, 1)}
                  disabled={value[row.key] >= 9}
                  className="h-8 w-8 rounded-full border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center"
                  aria-label={`Increase ${row.label}`}
                  data-testid={`${row.key}-increase`}
                >+</button>
              </div>
            </div>
          ))}
          <button
            onClick={() => setOpen(false)}
            className="mt-2 w-full rounded-md bg-[#1a73e8] py-2 text-sm text-white hover:bg-[#1765cc] cursor-pointer"
            data-testid="passenger-done"
          >Done</button>
        </div>
      )}
    </div>
  );
}
