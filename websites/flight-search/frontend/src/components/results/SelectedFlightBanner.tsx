import type { FlightOffer } from '../../api/types';
import { useCurrency } from '../../contexts/CurrencyContext';
import { formatDuration, formatStops, formatTime } from '../../utils/format';

interface Props {
  flight: FlightOffer;
  onChangeClick: () => void;
  label?: string;
}

export default function SelectedFlightBanner({ flight, onChangeClick, label }: Props) {
  const { formatPrice } = useCurrency();
  const airlineNames = [...new Set(flight.segments.map(s => s.airline_name))];

  return (
    <div
      className="mb-4 flex items-center justify-between rounded-lg border border-blue-200 bg-blue-50 px-4 py-3"
      data-testid="selected-flight-banner"
    >
      <div className="flex items-center gap-4 min-w-0">
        {/* Label */}
        {label && (
          <span className="text-xs font-semibold text-[#1a73e8] uppercase tracking-wide flex-shrink-0">
            {label}
          </span>
        )}
        {/* Airline badge */}
        <div className="flex h-8 w-8 items-center justify-center rounded bg-white text-[11px] font-bold text-gray-600 flex-shrink-0">
          {flight.segments[0].airline_code}
        </div>

        {/* Flight summary */}
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
            <span>{formatTime(flight.departure)}</span>
            <span className="text-gray-400">&ndash;</span>
            <span>{formatTime(flight.arrival)}</span>
          </div>
          <div className="text-xs text-gray-500 truncate">
            {airlineNames.join(', ')} · {formatDuration(flight.total_duration_minutes)} · {formatStops(flight.stops)}
          </div>
        </div>

        {/* Price */}
        <div className="text-sm font-medium text-gray-900 flex-shrink-0 ml-2">
          {formatPrice(flight.price_usd)}
        </div>
      </div>

      {/* Change button */}
      <button
        onClick={onChangeClick}
        className="ml-4 flex-shrink-0 rounded-full border border-[#1a73e8] px-4 py-1.5 text-sm font-medium text-[#1a73e8] hover:bg-blue-50 cursor-pointer"
        data-testid="change-outbound-btn"
      >
        Change
      </button>
    </div>
  );
}
