import { useNavigate } from 'react-router-dom';
import { useCurrency } from '../../contexts/CurrencyContext';

export default function Header() {
  const navigate = useNavigate();
  const { currency, setCurrency, currencies, symbols } = useCurrency();

  return (
    <header className="border-b border-gray-200 bg-white" data-testid="header">
      <div className="mx-auto max-w-7xl px-4 py-3 flex items-center justify-between">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-xl font-medium text-gray-900 hover:opacity-80 cursor-pointer"
          data-testid="logo"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="text-[#1a73e8]">
            <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" fill="currentColor"/>
          </svg>
          Flights
        </button>

        <div className="flex items-center gap-2">
          <svg className="h-4 w-4 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z" />
          </svg>
          <select
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-700 hover:border-gray-400 focus:border-[#1a73e8] focus:outline-none cursor-pointer"
            data-testid="currency-selector"
          >
            {currencies.map((c) => (
              <option key={c} value={c}>
                {symbols[c] ?? c} {c}
              </option>
            ))}
          </select>
        </div>
      </div>
    </header>
  );
}
