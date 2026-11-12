import { useLocation, useNavigate } from 'react-router-dom';
import type { BookingResponse, FlightOffer } from '../api/types';
import { useCurrency } from '../contexts/CurrencyContext';
import { formatDate, formatDuration, formatStops, formatTime } from '../utils/format';

interface LocationState {
  booking: BookingResponse;
}

function FlightDetail({ label, flight }: { label: string; flight: FlightOffer }) {
  const { formatPrice } = useCurrency();
  const firstSeg = flight.segments[0];
  const lastSeg = flight.segments[flight.segments.length - 1];
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
      <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">{label}</div>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-gray-900">
            {formatTime(flight.departure)} &ndash; {formatTime(flight.arrival)}
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            {firstSeg.origin_city} ({flight.origin}) &rarr; {lastSeg.destination_city} ({flight.destination})
          </div>
          <div className="text-xs text-gray-400 mt-0.5">
            {formatDate(flight.departure)} &middot; {formatDuration(flight.total_duration_minutes)} &middot; {formatStops(flight.stops)}
          </div>
          <div className="text-xs text-gray-400 mt-0.5">
            {firstSeg.airline_name} {firstSeg.flight_number}
          </div>
        </div>
        <div className="text-right">
          <div className="text-lg font-semibold text-gray-900">{formatPrice(flight.price_usd)}</div>
        </div>
      </div>
    </div>
  );
}

export default function ConfirmationPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { formatPrice } = useCurrency();
  const state = location.state as LocationState | null;

  if (!state?.booking) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 text-center">
        <h1 className="text-xl font-semibold text-gray-900 mb-2">No booking found</h1>
        <p className="text-gray-500 mb-4">Please search for flights and complete a booking.</p>
        <button onClick={() => navigate('/')} className="text-[#1a73e8] hover:underline cursor-pointer">
          Back to search
        </button>
      </div>
    );
  }

  const { booking } = state;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      {/* Success banner */}
      <div className="mb-8 rounded-lg bg-green-50 border border-green-200 p-6 text-center">
        <svg className="mx-auto h-12 w-12 text-green-500 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h1 className="text-2xl font-semibold text-green-800">Booking confirmed!</h1>
        <p className="text-green-700 mt-1">
          Booking ID: <span className="font-mono font-semibold">{booking.booking_id}</span>
        </p>
      </div>

      {/* Flight details */}
      <section className="mb-8">
        <h2 className="text-lg font-medium text-gray-900 mb-3">Flight details</h2>
        <div className="space-y-3">
          {booking.multi_city_flights && booking.multi_city_flights.length >= 2 ? (
            booking.multi_city_flights.map((flight, i) => (
              <FlightDetail key={i} label={`Flight ${i + 1}`} flight={flight} />
            ))
          ) : (
            <>
              <FlightDetail label="Outbound flight" flight={booking.outbound_flight} />
              {booking.return_flight && (
                <FlightDetail label="Return flight" flight={booking.return_flight} />
              )}
            </>
          )}
        </div>
      </section>

      {/* Passenger info */}
      <section className="mb-8">
        <h2 className="text-lg font-medium text-gray-900 mb-3">Passenger</h2>
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700 space-y-1">
          <div>{booking.passenger.first_name} {booking.passenger.last_name}</div>
          <div className="text-gray-500">{booking.passenger.email}</div>
          <div className="text-gray-500">{booking.passenger.phone}</div>
        </div>
      </section>

      {/* Payment summary */}
      <section className="mb-8">
        <h2 className="text-lg font-medium text-gray-900 mb-3">Payment</h2>
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-sm text-gray-700 space-y-1">
          <div>{booking.payment_summary.card_type} {booking.payment_summary.masked_card}</div>
          <div className="text-gray-500">{booking.payment_summary.cardholder_name}</div>
          <div className="text-lg font-semibold text-gray-900 mt-2">
            Total charged: {formatPrice(booking.total_price)}
          </div>
        </div>
      </section>

      <button
        onClick={() => navigate('/')}
        className="w-full rounded-lg bg-[#1a73e8] py-3 text-sm font-medium text-white hover:bg-[#1557b0] cursor-pointer"
      >
        Back to search
      </button>
    </div>
  );
}
