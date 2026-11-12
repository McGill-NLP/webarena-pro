import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { FlightOffer } from '../api/types';
import { bookFlight } from '../api/client';
import { useCurrency } from '../contexts/CurrencyContext';
import { formatDate, formatDuration, formatStops, formatTime } from '../utils/format';

interface SelectedFare {
  tier: string;
  label: string;
  totalPrice: number;
}

interface LocationState {
  outboundFlight: FlightOffer;
  returnFlight?: FlightOffer;
  multiCityFlights?: FlightOffer[];
  selectedFare?: SelectedFare;
}

function FlightSummaryCard({ label, flight }: { label: string; flight: FlightOffer }) {
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

export default function BookingPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { formatPrice } = useCurrency();
  const state = location.state as LocationState | null;

  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [cardNumber, setCardNumber] = useState('');
  const [expiry, setExpiry] = useState('');
  const [cvv, setCvv] = useState('');
  const [cardholderName, setCardholderName] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (!state?.outboundFlight) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 text-center">
        <h1 className="text-xl font-semibold text-gray-900 mb-2">No flight selected</h1>
        <p className="text-gray-500 mb-4">Please search for flights and select one to book.</p>
        <button onClick={() => navigate('/')} className="text-[#1a73e8] hover:underline cursor-pointer">
          Back to search
        </button>
      </div>
    );
  }

  const { outboundFlight, returnFlight, multiCityFlights, selectedFare } = state;
  const isMultiCity = multiCityFlights && multiCityFlights.length >= 2;
  const totalPrice = selectedFare?.totalPrice ?? (
    isMultiCity
      ? multiCityFlights.reduce((sum, f) => sum + f.price_usd, 0)
      : outboundFlight.price_usd + (returnFlight?.price_usd || 0)
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const response = await bookFlight({
        passenger: { first_name: firstName, last_name: lastName, email, phone },
        payment: { card_number: cardNumber, expiry_date: expiry, cvv, cardholder_name: cardholderName },
        outbound_flight: outboundFlight,
        return_flight: returnFlight || null,
        multi_city_flights: isMultiCity ? multiCityFlights : undefined,
        total_price: totalPrice,
      });
      navigate('/confirmation', { state: { booking: response } });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Booking failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Complete your booking</h1>

      {/* Flight summary */}
      <div className="space-y-3 mb-8">
        {isMultiCity ? (
          multiCityFlights.map((flight, i) => (
            <FlightSummaryCard key={i} label={`Flight ${i + 1}`} flight={flight} />
          ))
        ) : (
          <>
            <FlightSummaryCard label="Outbound flight" flight={outboundFlight} />
            {returnFlight && <FlightSummaryCard label="Return flight" flight={returnFlight} />}
          </>
        )}
        {selectedFare && (
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 flex items-center justify-between">
            <div className="text-sm text-gray-700">
              <span className="font-medium">{selectedFare.label}</span>
              <span className="text-gray-400 ml-1">fare selected</span>
            </div>
            <button
              onClick={() => navigate(-1)}
              className="text-xs text-[#1a73e8] hover:underline cursor-pointer"
            >
              Change
            </button>
          </div>
        )}
        <div className="text-right text-lg font-semibold text-gray-900">
          Total: {formatPrice(totalPrice)}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-6 rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700" data-testid="booking-error">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Passenger info */}
        <section>
          <h2 className="text-lg font-medium text-gray-900 mb-4">Passenger information</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">First name</label>
              <input
                type="text" required value={firstName} onChange={e => setFirstName(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#1a73e8] focus:outline-none focus:ring-1 focus:ring-[#1a73e8]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Last name</label>
              <input
                type="text" required value={lastName} onChange={e => setLastName(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#1a73e8] focus:outline-none focus:ring-1 focus:ring-[#1a73e8]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email" required value={email} onChange={e => setEmail(e.target.value)}
                placeholder="john@example.com"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#1a73e8] focus:outline-none focus:ring-1 focus:ring-[#1a73e8]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
              <input
                type="tel" required value={phone} onChange={e => setPhone(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#1a73e8] focus:outline-none focus:ring-1 focus:ring-[#1a73e8]"
              />
            </div>
          </div>
        </section>

        {/* Payment info */}
        <section>
          <h2 className="text-lg font-medium text-gray-900 mb-4">Payment information</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Card number</label>
              <input
                type="text" required value={cardNumber} onChange={e => setCardNumber(e.target.value)}
                placeholder="4111111111111111"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#1a73e8] focus:outline-none focus:ring-1 focus:ring-[#1a73e8]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Expiry date</label>
              <input
                type="text" required value={expiry} onChange={e => setExpiry(e.target.value)}
                placeholder="MM/YY"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#1a73e8] focus:outline-none focus:ring-1 focus:ring-[#1a73e8]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">CVV</label>
              <input
                type="text" required value={cvv} onChange={e => setCvv(e.target.value)}
                placeholder="123"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#1a73e8] focus:outline-none focus:ring-1 focus:ring-[#1a73e8]"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Cardholder name</label>
              <input
                type="text" required value={cardholderName} onChange={e => setCardholderName(e.target.value)}
                placeholder="John Smith"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#1a73e8] focus:outline-none focus:ring-1 focus:ring-[#1a73e8]"
              />
            </div>
          </div>
        </section>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-[#1a73e8] py-3 text-sm font-medium text-white hover:bg-[#1557b0] disabled:opacity-50 cursor-pointer"
        >
          {submitting ? 'Processing...' : `Pay ${formatPrice(totalPrice)}`}
        </button>
      </form>
    </div>
  );
}
