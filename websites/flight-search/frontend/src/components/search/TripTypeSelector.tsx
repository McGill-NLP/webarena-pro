import type { TripType } from '../../api/types';

const OPTIONS: { value: TripType; label: string }[] = [
  { value: 'round_trip', label: 'Round trip' },
  { value: 'one_way', label: 'One way' },
  { value: 'multi_city', label: 'Multi-city' },
];

interface Props {
  value: TripType;
  onChange: (v: TripType) => void;
}

export default function TripTypeSelector({ value, onChange }: Props) {
  return (
    <div className="relative" data-testid="trip-type-selector">
      <select
        value={value}
        onChange={e => onChange(e.target.value as TripType)}
        className="appearance-none rounded-md border border-gray-300 bg-white px-3 py-2 pr-8 text-sm text-gray-700 hover:border-gray-400 focus:border-[#1a73e8] focus:outline-none cursor-pointer"
        aria-label="Trip type"
        data-testid="trip-type-select"
      >
        {OPTIONS.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <svg className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd"/>
      </svg>
    </div>
  );
}
