import type { SortBy } from '../../api/types';

const OPTIONS: { value: SortBy; label: string }[] = [
  { value: 'best', label: 'Best' },
  { value: 'cheapest', label: 'Cheapest' },
  { value: 'fastest', label: 'Fastest' },
];

interface Props {
  value: SortBy;
  onChange: (v: SortBy) => void;
  resultCount: number;
}

export default function SortBar({ value, onChange, resultCount }: Props) {
  return (
    <div className="flex items-center justify-between" data-testid="sort-bar">
      <span className="text-sm text-gray-500" data-testid="result-count">
        {resultCount} result{resultCount !== 1 ? 's' : ''}
      </span>
      <div className="flex gap-1 rounded-lg bg-gray-100 p-1">
        {OPTIONS.map(o => (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors cursor-pointer ${
              value === o.value
                ? 'bg-white text-[#1a73e8] shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
            data-testid={`sort-${o.value}`}
            aria-pressed={value === o.value}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
