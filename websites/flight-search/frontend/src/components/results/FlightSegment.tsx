import type { FlightSegment as SegmentType } from '../../api/types';
import { formatDuration, formatTime } from '../../utils/format';

interface Props {
  segment: SegmentType;
  showDetails?: boolean;
}

export default function FlightSegmentView({ segment, showDetails }: Props) {
  return (
    <div className="flex items-center gap-4 py-2" data-testid="flight-segment">
      {/* Airline badge */}
      <div className="flex h-9 w-9 items-center justify-center rounded bg-gray-100 text-xs font-bold text-gray-600 flex-shrink-0" data-testid="airline-badge">
        {segment.airline_code}
      </div>

      {/* Timeline */}
      <div className="flex flex-1 items-center gap-3">
        <div className="text-right min-w-[70px]">
          <div className="text-base font-medium" data-testid="departure-time">{formatTime(segment.departure)}</div>
          <div className="text-xs text-gray-500" data-testid="origin-code">{segment.origin}</div>
        </div>

        <div className="flex flex-1 flex-col items-center px-2">
          <div className="text-xs text-gray-500">{formatDuration(segment.duration_minutes)}</div>
          <div className="relative my-1 h-px w-full bg-gray-300">
            <div className="absolute left-0 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full border-2 border-gray-400 bg-white" />
            <div className="absolute right-0 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full border-2 border-gray-400 bg-white" />
          </div>
          {showDetails && (
            <div className="text-xs text-gray-400">{segment.airline_name} · {segment.flight_number} · {segment.aircraft}</div>
          )}
        </div>

        <div className="min-w-[70px]">
          <div className="text-base font-medium" data-testid="arrival-time">{formatTime(segment.arrival)}</div>
          <div className="text-xs text-gray-500" data-testid="destination-code">{segment.destination}</div>
        </div>
      </div>
    </div>
  );
}
