import { useState } from 'react';
import type { FlightOffer } from '../../api/types';
import { useCurrency } from '../../contexts/CurrencyContext';
import { daysBetween, formatDuration, formatStops, formatTime } from '../../utils/format';

interface Props {
  flight: FlightOffer;
  roundTripPrice?: number | null;
  priceLabel?: string;
  onSelect?: (flight: FlightOffer) => void;
  onBook?: (flight: FlightOffer) => void;
  discountApplied?: boolean;
}

function WarningIndicator({ text }: { text: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-amber-600 align-baseline">
      <span className="text-gray-300">·</span>
      <span>{text}</span>
      <svg className="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
        <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>
      </svg>
    </span>
  );
}

export default function FlightCard({ flight, roundTripPrice, priceLabel, onSelect, onBook, discountApplied }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { formatPrice } = useCurrency();
  const firstSeg = flight.segments[0];

  // Compare calendar dates in their respective local timezones (not browser TZ)
  const daysDiff = daysBetween(flight.departure, flight.arrival);

  // All airlines in this itinerary
  const airlineNames = [...new Set(flight.segments.map(s => s.airline_name))];
  // Layover airports for connecting flights
  const layoverAirports = flight.segments.slice(0, -1).map(s => s.destination);

  return (
    <div
      className="rounded-lg border border-gray-200 bg-white hover:shadow-md transition-shadow cursor-pointer"
      onClick={() => setExpanded(!expanded)}
      data-testid={`flight-card-${flight.id}`}
      role="article"
      aria-label={`Flight from ${flight.origin} to ${flight.destination}, ${formatPrice(flight.price_usd)}`}
    >
      <div className="grid items-center p-4" style={{ gridTemplateColumns: '40px 1fr auto 20px' }}>
        {/* Airline badge */}
        <div className="flex h-9 w-9 items-center justify-center rounded bg-gray-100 text-[11px] font-bold text-gray-600 self-start mt-0.5" data-testid="airline-badge">
          {firstSeg.airline_code}
        </div>

        {/* Center: times + route info */}
        <div className="ml-3 mr-4">
          {/* Row 1: dep time – arr time, duration, stops */}
          <div className="flex items-baseline gap-1 flex-wrap">
            <span className="text-[15px] font-medium whitespace-nowrap" data-testid="departure-time">
              {formatTime(flight.departure)}
            </span>
            <span className="text-gray-400 text-sm">&ndash;</span>
            <span className="text-[15px] font-medium whitespace-nowrap" data-testid="arrival-time">
              {formatTime(flight.arrival)}{daysDiff > 0 && <sup className="text-[10px] text-red-500 ml-px">+{daysDiff}</sup>}
            </span>
          </div>

          {/* Row 2: airline names */}
          <div className="text-xs text-gray-500 mt-0.5 truncate" data-testid="airline-name">
            {airlineNames.join(', ')}
          </div>

          {/* Row 3: duration + stops + stop cities + emissions */}
          <div className="flex items-center gap-1.5 mt-0.5 text-xs text-gray-500 flex-wrap">
            <span>{formatDuration(flight.total_duration_minutes)}</span>
            <span className="text-gray-300">·</span>
            <span data-testid="stops">{formatStops(flight.stops)}</span>
            {layoverAirports.length > 0 && (
              <>
                <span className="text-gray-300">·</span>
                <span className="text-gray-500">{layoverAirports.join(', ')}</span>
              </>
            )}
            {flight.emissions_kg > 0 && (
              <>
                <span className="text-gray-300">·</span>
                <span className="text-gray-400">{flight.emissions_kg} kg CO₂</span>
              </>
            )}
          </div>
        </div>

        {/* Select button + Price column */}
        <div className="flex items-center gap-3 pl-3">
          {onSelect && expanded && (
            <button
              onClick={(e) => { e.stopPropagation(); onSelect(flight); }}
              className="rounded-full bg-[#1a73e8] px-4 py-1.5 text-xs font-medium text-white hover:bg-[#1557b0] cursor-pointer whitespace-nowrap"
              data-testid="select-flight-btn"
            >
              Select flight
            </button>
          )}
          {onBook && expanded && (
            <button
              onClick={(e) => { e.stopPropagation(); onBook(flight); }}
              className="rounded-full bg-[#1a73e8] px-4 py-1.5 text-xs font-medium text-white hover:bg-[#1557b0] cursor-pointer whitespace-nowrap"
              data-testid="book-flight-btn"
            >
              Book
            </button>
          )}
          <div className="text-right min-w-[80px]" data-testid="price">
            {roundTripPrice != null ? (
              <>
                <div className="text-[15px] font-medium text-gray-900">{formatPrice(roundTripPrice)}</div>
                <div className="text-[11px] text-gray-500">{priceLabel || 'round trip'}</div>
              </>
            ) : (
              <>
                <div className="text-[15px] font-medium text-gray-900">{formatPrice(flight.price_usd)}</div>
                <div className="text-[11px] text-gray-500">{flight.cabin_class.replace('_', ' ')}</div>
              </>
            )}
            {discountApplied && (
              <div className="text-[10px] text-green-600 mt-0.5">Airline discount</div>
            )}
          </div>
        </div>

        {/* Chevron */}
        <svg
          className={`h-5 w-5 text-gray-400 transition-transform ml-1 ${expanded ? 'rotate-180' : ''}`}
          viewBox="0 0 20 20" fill="currentColor"
        >
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd"/>
        </svg>
      </div>

      {/* Expanded detail view */}
      {expanded && (
        <div className="border-t border-gray-100 px-4 pt-3 pb-4" data-testid="segments-detail">
          {flight.segments.map((seg, i) => (
            <div key={i}>
              {/* Segment: timeline+info on left, amenities on right */}
              <div className="flex gap-4">
                {/* Left side: timeline + segment content */}
                <div className="flex gap-3 flex-1 min-w-0">
                  {/* Timeline column */}
                  <div className="flex flex-col items-center w-5 flex-shrink-0">
                    <div className="h-2.5 w-2.5 rounded-full border-2 border-[#1a73e8] bg-white" />
                    <div className="flex-1 w-px bg-gray-300 my-0.5" />
                    <div className="h-2.5 w-2.5 rounded-full border-2 border-[#1a73e8] bg-white" />
                  </div>

                  {/* Segment content */}
                  <div className="flex-1 pb-1 min-w-0">
                    {/* Departure */}
                    <div className="flex items-baseline gap-2">
                      <span className="text-sm font-medium w-16 flex-shrink-0">{formatTime(seg.departure)}</span>
                      <span className="text-sm text-gray-500">·</span>
                      <span className="text-sm text-gray-900">{seg.origin_city} ({seg.origin})</span>
                    </div>

                    {/* Flight info line */}
                    <div className="ml-[72px] my-1.5 text-xs text-gray-400 leading-relaxed">
                      <div>
                        Travel time: {formatDuration(seg.duration_minutes)}
                        {seg.is_overnight && <WarningIndicator text="Overnight" />}
                      </div>
                      <div>{seg.airline_name} · {seg.flight_number} · {seg.aircraft}</div>
                    </div>

                    {/* Arrival */}
                    <div className="flex items-baseline gap-2">
                      <span className="text-sm font-medium w-16 flex-shrink-0">{formatTime(seg.arrival)}</span>
                      <span className="text-sm text-gray-500">·</span>
                      <span className="text-sm text-gray-900">{seg.destination_city} ({seg.destination})</span>
                    </div>
                  </div>
                </div>

                {/* Right side: amenities */}
                <div className="flex-shrink-0 w-44 border-l border-gray-100 pl-4 text-xs text-gray-500 space-y-1.5 pt-0.5" data-testid="segment-amenities">
                  {/* Legroom */}
                  <div className="flex items-center gap-2">
                    <svg className="h-4 w-4 text-gray-400 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M6 19v-4a2 2 0 012-2h1V7a2 2 0 012-2h2a2 2 0 012 2v6h1a2 2 0 012 2v4" strokeLinecap="round" strokeLinejoin="round"/>
                      <path d="M6 19h12" strokeLinecap="round"/>
                    </svg>
                    <span>{seg.legroom_inches} in legroom</span>
                  </div>

                  {/* WiFi */}
                  <div className="flex items-center gap-2">
                    {seg.has_wifi ? (
                      <>
                        <svg className="h-4 w-4 text-gray-400 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M1 9l2 2c4.97-4.97 13.03-4.97 18 0l2-2C16.93 2.93 7.08 2.93 1 9zm8 8l3 3 3-3c-1.65-1.66-4.34-1.66-6 0zm-4-4l2 2c2.76-2.76 7.24-2.76 10 0l2-2C15.14 9.14 8.87 9.14 5 13z"/>
                        </svg>
                        <span>{seg.wifi_type || 'Wi-Fi'}</span>
                      </>
                    ) : (
                      <>
                        <svg className="h-4 w-4 text-gray-300 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M1 9l2 2c4.97-4.97 13.03-4.97 18 0l2-2C16.93 2.93 7.08 2.93 1 9zm8 8l3 3 3-3c-1.65-1.66-4.34-1.66-6 0zm-4-4l2 2c2.76-2.76 7.24-2.76 10 0l2-2C15.14 9.14 8.87 9.14 5 13z"/>
                        </svg>
                        <span className="text-gray-300 line-through">Wi-Fi</span>
                      </>
                    )}
                  </div>

                  {/* Power & USB */}
                  <div className="flex items-center gap-2">
                    {(seg.has_power || seg.has_usb) ? (
                      <>
                        <svg className="h-4 w-4 text-gray-400 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M7 2v11h3v9l7-12h-4l4-8z"/>
                        </svg>
                        <span>
                          {seg.has_power && seg.has_usb
                            ? 'Power & USB'
                            : seg.has_power
                              ? 'In-seat power'
                              : 'USB charging'}
                        </span>
                      </>
                    ) : (
                      <>
                        <svg className="h-4 w-4 text-gray-300 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M7 2v11h3v9l7-12h-4l4-8z"/>
                        </svg>
                        <span className="text-gray-300 line-through">Power</span>
                      </>
                    )}
                  </div>

                  {/* Video/Entertainment */}
                  <div className="flex items-center gap-2">
                    {seg.has_video ? (
                      <>
                        <svg className="h-4 w-4 text-gray-400 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h5v2h8v-2h5c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 14H3V5h18v12z"/>
                        </svg>
                        <span>{seg.video_type || 'On-demand video'}</span>
                      </>
                    ) : (
                      <>
                        <svg className="h-4 w-4 text-gray-300 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h5v2h8v-2h5c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 14H3V5h18v12z"/>
                        </svg>
                        <span className="text-gray-300 line-through">Entertainment</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Layover between segments */}
              {flight.layovers[i] && (
                <div className="flex gap-3 my-2">
                  <div className="w-5 flex-shrink-0" />
                  <div className="flex-1 rounded-md bg-gray-50 border border-gray-200 px-3 py-2">
                    <span className="text-xs text-gray-500">
                      {formatDuration(flight.layovers[i].duration_minutes)} layover
                      · {flight.layovers[i].airport_city} ({flight.layovers[i].airport})
                      {flight.layovers[i].is_overnight && <WarningIndicator text="Overnight layover" />}
                      {flight.layovers[i].is_short_connection && <WarningIndicator text="Short connection" />}
                    </span>
                  </div>
                </div>
              )}
            </div>
          ))}

          {/* Bottom info: emissions + cabin class + total travel time */}
          <div className="mt-3 pt-3 border-t border-gray-100 flex items-center gap-4 text-xs text-gray-400">
            <span>Total travel time: {formatDuration(flight.total_duration_minutes)}</span>
            {flight.emissions_kg > 0 && (
              <>
                <span>·</span>
                <svg className="h-3.5 w-3.5 inline text-green-500" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M17 8C8 10 5.9 16.17 3.82 21.34l1.89.66.95-2.3c.48.17.98.3 1.34.3C19 20 22 3 22 3c-1 2-8 2.25-13 3.25S2 11.5 2 13.5s1.75 3.75 1.75 3.75C7 8 17 8 17 8z"/>
                </svg>
                <span className="text-green-600">{flight.emissions_kg} kg CO₂</span>
              </>
            )}
          </div>

        </div>
      )}
    </div>
  );
}
