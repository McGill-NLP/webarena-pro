import { useEffect, useId, useRef, useState } from 'react';
import { searchAirports } from '../../api/client';
import type { AutocompleteResult } from '../../api/types';
import { useDebounce } from '../../hooks/useDebounce';
import { extractIataFromText } from '../../utils/airport';

interface Props {
  label: string;
  value: string;          // IATA code
  displayValue: string;   // "New York (JFK)"
  onChange: (iata: string, display: string) => void;
  placeholder?: string;
  testId?: string;
}

export default function AirportInput({ label, value, displayValue, onChange, placeholder, testId }: Props) {
  const query = displayValue;
  const [lookup, setLookup] = useState<{
    query: string;
    results: AutocompleteResult[];
    error: string;
  } | null>(null);
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const results = lookup?.query === query ? lookup.results : [];
  const error = lookup?.query === query ? lookup.error : '';
  const errorId = useId();
  const debouncedQuery = useDebounce(query, 200);
  const onChangeRef = useRef(onChange);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  // Only exact matches from the airport API can become submitted IATA codes.
  // Include the live query so edits immediately cancel stale debounced lookups.
  useEffect(() => {
    if (query !== debouncedQuery || !query.trim()) return;
    let cancelled = false;
    const typedIata = extractIataFromText(query);
    searchAirports(typedIata || query.trim()).then(r => {
      if (!cancelled) {
        setLookup({ query, results: r, error: r.length ? '' : 'No matching airports. Choose a specific city or airport.' });
        setOpen(r.length > 0);
        if (typedIata) {
          const airport = r.find(result => result.iata === typedIata);
          onChangeRef.current(airport?.iata || '', query);
        }
      }
    }).catch(() => {
      if (!cancelled) {
        setLookup({ query, results: [], error: 'Unable to look up airports. Edit the field to try again.' });
      }
    });
    return () => { cancelled = true; };
  }, [debouncedQuery, query]);

  function select(r: AutocompleteResult) {
    onChange(r.iata, `${r.city_name} (${r.iata})`);
    setOpen(false);
    setFocused(false);
  }

  function handleInputChange(text: string) {
    setFocused(true);
    setOpen(true);
    // Preserve the user's text, but disable Search until this edit is validated.
    onChange('', text);
  }

  return (
    <div className="relative flex-1 min-w-[180px]" data-testid={testId}>
      <label className="absolute -top-2 left-3 bg-white px-1 text-xs text-gray-500 z-10">{label}</label>
      <input
        type="text"
        value={query}
        onChange={e => handleInputChange(e.target.value)}
        onFocus={e => { setFocused(true); setOpen(true); e.target.select(); }}
        onBlur={() => { setFocused(false); setOpen(false); }}
        placeholder={placeholder || 'City or airport'}
        className="w-full rounded-md border border-gray-300 px-3 py-3 text-sm text-gray-900 placeholder-gray-400 hover:border-gray-400 focus:border-[#1a73e8] focus:outline-none"
        aria-label={label}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : undefined}
        data-testid={testId ? `${testId}-input` : undefined}
        autoComplete="off"
      />
      {error && (
        <p id={errorId} role="status" className="mt-1 text-xs text-red-600">{error}</p>
      )}
      {focused && open && results.length > 0 && (
        <ul
          className="absolute top-full left-0 right-0 z-50 mt-1 max-h-64 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg"
          data-testid={testId ? `${testId}-dropdown` : undefined}
          role="listbox"
        >
          {results.map(r => (
            <li
              key={r.iata}
              onMouseDown={e => e.preventDefault()}
              onClick={() => select(r)}
              className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-gray-50"
              role="option"
              data-testid={`airport-option-${r.iata}`}
              aria-selected={r.iata === value}
            >
              <svg className="h-5 w-5 flex-shrink-0 text-gray-400" viewBox="0 0 24 24" fill="none">
                <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" fill="currentColor"/>
              </svg>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-gray-900 truncate">{r.city_name} ({r.iata})</div>
                <div className="text-xs text-gray-500 truncate">{r.name}, {r.country}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
