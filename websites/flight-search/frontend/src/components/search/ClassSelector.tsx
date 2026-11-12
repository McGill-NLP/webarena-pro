import type { CabinClass } from '../../api/types';
import { cabinClassLabel } from '../../utils/format';

const OPTIONS: CabinClass[] = ['economy', 'premium_economy', 'business', 'first'];

interface Props {
  value: CabinClass;
  onChange: (v: CabinClass) => void;
}

export default function ClassSelector({ value, onChange }: Props) {
  return (
    <div className="relative" data-testid="class-selector">
      <select
        value={value}
        onChange={e => onChange(e.target.value as CabinClass)}
        className="appearance-none rounded-md border border-gray-300 bg-white px-3 py-2 pr-8 text-sm text-gray-700 hover:border-gray-400 focus:border-[#1a73e8] focus:outline-none cursor-pointer"
        aria-label="Cabin class"
        data-testid="class-select"
      >
        {OPTIONS.map(c => (
          <option key={c} value={c}>{cabinClassLabel(c)}</option>
        ))}
      </select>
      <svg className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd"/>
      </svg>
    </div>
  );
}
