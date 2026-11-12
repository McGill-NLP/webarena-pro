import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { FlightOffer } from '../api/types';
import { useCurrency } from '../contexts/CurrencyContext';
import { formatDate, formatDuration, formatStops, formatTime } from '../utils/format';

interface LocationState {
  outboundFlight: FlightOffer;
  returnFlight?: FlightOffer;
  multiCityFlights?: FlightOffer[];
  basePrice?: number;
}

type FeatureStatus = 'included' | 'paid' | 'none';

interface FeatureEntry {
  status: FeatureStatus;
  label: string;
}

interface TierConfig {
  key: string;
  label: string;
  description: string;
  priceMultiplier: number;
  features: FeatureEntry[];
  isUpgrade?: boolean;
}

interface CabinConfig {
  tiers: TierConfig[];
  featureCount: number;
}

// Feature slot order: seat_selection, seat_comfort, priority_boarding,
// ticket_changes, ticket_cancellation, carry_on, checked_bag

const ECONOMY_CONFIG: CabinConfig = {
  featureCount: 7,
  tiers: [
    {
      key: 'basic', label: 'Basic Economy', description: 'Most restrictions apply', priceMultiplier: 1.0,
      features: [
        { status: 'paid', label: 'Seat selection' },
        { status: 'none', label: 'Extra legroom' },
        { status: 'none', label: 'Priority boarding' },
        { status: 'none', label: 'Ticket changes' },
        { status: 'none', label: 'Ticket cancellation' },
        { status: 'none', label: 'Carry-on' },
        { status: 'paid', label: '1 pc checked bag' },
      ],
    },
    {
      key: 'standard', label: 'Economy', description: 'Standard ticket with flexibility', priceMultiplier: 1.12,
      features: [
        { status: 'included', label: 'Seat selection' },
        { status: 'paid', label: 'Extra legroom' },
        { status: 'none', label: 'Priority boarding' },
        { status: 'paid', label: 'Ticket changes' },
        { status: 'paid', label: 'Ticket cancellation' },
        { status: 'included', label: 'Carry-on' },
        { status: 'paid', label: '1 pc checked bag' },
      ],
    },
    {
      key: 'flex', label: 'Economy Flex', description: 'Full flexibility included', priceMultiplier: 1.32,
      features: [
        { status: 'included', label: 'Seat selection' },
        { status: 'included', label: 'Extra legroom' },
        { status: 'included', label: 'Priority boarding' },
        { status: 'included', label: 'Free ticket changes' },
        { status: 'included', label: 'Free ticket cancellation' },
        { status: 'included', label: 'Carry-on' },
        { status: 'included', label: '1 pc checked bag' },
      ],
    },
  ],
};

const PREMIUM_ECONOMY_CONFIG: CabinConfig = {
  featureCount: 7,
  tiers: [
    {
      key: 'standard', label: 'Premium Economy', description: 'Standard ticket with comfort', priceMultiplier: 1.0,
      features: [
        { status: 'included', label: 'Seat selection' },
        { status: 'included', label: 'Extra legroom' },
        { status: 'included', label: 'Priority boarding' },
        { status: 'paid', label: 'Ticket changes' },
        { status: 'paid', label: 'Ticket cancellation' },
        { status: 'included', label: 'Carry-on' },
        { status: 'included', label: '1 pc checked bag' },
      ],
    },
    {
      key: 'flex', label: 'Premium Economy Flex', description: 'Full flexibility included', priceMultiplier: 1.18,
      features: [
        { status: 'included', label: 'Seat selection' },
        { status: 'included', label: 'Extra legroom' },
        { status: 'included', label: 'Priority boarding' },
        { status: 'included', label: 'Free ticket changes' },
        { status: 'included', label: 'Free ticket cancellation' },
        { status: 'included', label: 'Carry-on' },
        { status: 'included', label: '1 pc checked bag' },
      ],
    },
  ],
};

const BUSINESS_CONFIG: CabinConfig = {
  featureCount: 7,
  tiers: [
    {
      key: 'standard', label: 'Business', description: 'Standard business fare', priceMultiplier: 1.0,
      features: [
        { status: 'included', label: 'Seat selection' },
        { status: 'included', label: 'Lie-flat seat' },
        { status: 'included', label: 'Priority boarding' },
        { status: 'paid', label: 'Ticket changes' },
        { status: 'paid', label: 'Ticket cancellation' },
        { status: 'included', label: 'Carry-on' },
        { status: 'included', label: '2 pc checked bag' },
      ],
    },
    {
      key: 'flex', label: 'Business Flex', description: 'Full flexibility included', priceMultiplier: 1.15,
      features: [
        { status: 'included', label: 'Seat selection' },
        { status: 'included', label: 'Lie-flat seat' },
        { status: 'included', label: 'Priority boarding' },
        { status: 'included', label: 'Free ticket changes' },
        { status: 'included', label: 'Free ticket cancellation' },
        { status: 'included', label: 'Carry-on' },
        { status: 'included', label: '2 pc checked bag' },
      ],
    },
  ],
};

const FIRST_CONFIG: CabinConfig = {
  featureCount: 7,
  tiers: [
    {
      key: 'standard', label: 'First', description: 'Standard first class fare', priceMultiplier: 1.0,
      features: [
        { status: 'included', label: 'Seat selection' },
        { status: 'included', label: 'Lie-flat seat' },
        { status: 'included', label: 'Priority boarding' },
        { status: 'paid', label: 'Ticket changes' },
        { status: 'paid', label: 'Ticket cancellation' },
        { status: 'included', label: 'Carry-on' },
        { status: 'included', label: '2 pc checked bag' },
      ],
    },
    {
      key: 'flex', label: 'First Flex', description: 'Full flexibility included', priceMultiplier: 1.12,
      features: [
        { status: 'included', label: 'Seat selection' },
        { status: 'included', label: 'Lie-flat seat' },
        { status: 'included', label: 'Priority boarding' },
        { status: 'included', label: 'Free ticket changes' },
        { status: 'included', label: 'Free ticket cancellation' },
        { status: 'included', label: 'Carry-on' },
        { status: 'included', label: '2 pc checked bag' },
      ],
    },
  ],
};

const CABIN_ORDER: { key: string; config: CabinConfig; upgradeMultiplier: number }[] = [
  { key: 'economy', config: ECONOMY_CONFIG, upgradeMultiplier: 1.8 },
  { key: 'premium_economy', config: PREMIUM_ECONOMY_CONFIG, upgradeMultiplier: 2.2 },
  { key: 'business', config: BUSINESS_CONFIG, upgradeMultiplier: 1.6 },
  { key: 'first', config: FIRST_CONFIG, upgradeMultiplier: 1.0 },
];

function getCabinConfig(cabinClass: string): CabinConfig {
  const idx = CABIN_ORDER.findIndex(c => c.key === cabinClass);
  const current = idx >= 0 ? CABIN_ORDER[idx] : CABIN_ORDER[0];
  const next = idx >= 0 && idx < CABIN_ORDER.length - 1 ? CABIN_ORDER[idx + 1] : null;

  if (!next) return current.config;

  // Take the first (standard) tier from the next cabin as the upsell
  const upgradeTier = next.config.tiers[0];
  const upsellTier: TierConfig = {
    ...upgradeTier,
    key: `upgrade_${upgradeTier.key}`,
    priceMultiplier: current.upgradeMultiplier,
    isUpgrade: true,
  };

  return {
    featureCount: current.config.featureCount,
    tiers: [...current.config.tiers, upsellTier],
  };
}

function CheckIcon() {
  return (
    <svg className="h-5 w-5 text-[#1a73e8]" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
    </svg>
  );
}

function PaidIcon() {
  return (
    <svg className="h-5 w-5 text-gray-400" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v1H8a1 1 0 100 2h1v1H8a1 1 0 100 2h1v1a1 1 0 102 0v-1h1a1 1 0 100-2h-1V9h1a1 1 0 100-2h-1V6z" clipRule="evenodd" />
    </svg>
  );
}

function CrossIcon() {
  return (
    <svg className="h-5 w-5 text-gray-300" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
    </svg>
  );
}

function FeatureStatusIcon({ status }: { status: FeatureStatus }) {
  if (status === 'included') return <CheckIcon />;
  if (status === 'paid') return <PaidIcon />;
  return <CrossIcon />;
}

function FlightSummaryRow({ label, flight }: { label: string; flight: FlightOffer }) {
  const firstSeg = flight.segments[0];
  const lastSeg = flight.segments[flight.segments.length - 1];
  return (
    <div className="flex items-center gap-4 py-3">
      <div className="flex h-8 w-8 items-center justify-center rounded bg-gray-100 text-[10px] font-bold text-gray-600 flex-shrink-0">
        {firstSeg.airline_code}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-medium text-gray-900">{formatTime(flight.departure)}</span>
          <span className="text-gray-400">&ndash;</span>
          <span className="font-medium text-gray-900">{formatTime(flight.arrival)}</span>
          <span className="text-gray-300 text-xs">·</span>
          <span className="text-xs text-gray-500">{formatDuration(flight.total_duration_minutes)}</span>
          <span className="text-gray-300 text-xs">·</span>
          <span className="text-xs text-gray-500">{formatStops(flight.stops)}</span>
        </div>
        <div className="text-xs text-gray-500 mt-0.5">
          {firstSeg.origin_city} ({flight.origin}) &rarr; {lastSeg.destination_city} ({flight.destination})
          <span className="text-gray-300 mx-1">·</span>
          {formatDate(flight.departure)}
          <span className="text-gray-300 mx-1">·</span>
          {firstSeg.airline_name}
        </div>
      </div>
      <div className="text-xs font-medium text-gray-400 uppercase tracking-wide flex-shrink-0">
        {label}
      </div>
    </div>
  );
}

export default function BookingOptionsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { formatPrice } = useCurrency();
  const state = location.state as LocationState | null;
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

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

  const { outboundFlight, returnFlight, multiCityFlights, basePrice: passedBasePrice } = state;
  const isMultiCity = multiCityFlights && multiCityFlights.length >= 2;
  const cabinClass = outboundFlight.cabin_class;
  const config = getCabinConfig(cabinClass);
  const basePrice = passedBasePrice ?? (isMultiCity
    ? multiCityFlights.reduce((sum, f) => sum + f.price_usd, 0)
    : outboundFlight.price_usd + (returnFlight?.price_usd || 0));

  // Default to the first non-basic tier, or the first tier
  const defaultIndex = config.tiers.length > 2 ? 1 : 0;
  const selected = selectedIndex ?? defaultIndex;
  const selectedTier = config.tiers[selected];

  const tierPrices = config.tiers.map(t => Math.round(basePrice * t.priceMultiplier));
  const lowestPrice = tierPrices[0];

  function handleContinue() {
    navigate('/booking', {
      state: {
        outboundFlight,
        returnFlight,
        multiCityFlights,
        selectedFare: {
          tier: selectedTier.key,
          label: selectedTier.label,
          totalPrice: tierPrices[selected],
        },
      },
    });
  }

  const tierCount = config.tiers.length;
  const gridCols = tierCount === 4 ? 'grid-cols-4' : 'grid-cols-3';

  return (
    <div className="min-h-screen bg-gray-50">
      <div className={`mx-auto px-4 py-8 ${tierCount === 4 ? 'max-w-5xl' : 'max-w-4xl'}`}>
        {/* Back button */}
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1 text-sm text-[#1a73e8] hover:underline cursor-pointer mb-6"
        >
          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M12.79 5.23a.75.75 0 01-.02 1.06L8.832 10l3.938 3.71a.75.75 0 11-1.04 1.08l-4.5-4.25a.75.75 0 010-1.08l4.5-4.25a.75.75 0 011.06.02z" clipRule="evenodd" />
          </svg>
          Back to flights
        </button>

        {/* Flight summary */}
        <div className="rounded-lg border border-gray-200 bg-white p-5 mb-6">
          <h2 className="text-lg font-medium text-gray-900 mb-1">Selected flights</h2>
          <div className="divide-y divide-gray-100">
            {isMultiCity ? (
              multiCityFlights.map((flight, i) => (
                <FlightSummaryRow key={i} label={`Flight ${i + 1}`} flight={flight} />
              ))
            ) : (
              <>
                <FlightSummaryRow label="Departs" flight={outboundFlight} />
                {returnFlight && <FlightSummaryRow label="Returns" flight={returnFlight} />}
              </>
            )}
          </div>
        </div>

        {/* Fare options */}
        <h1 className="text-xl font-semibold text-gray-900 mb-2">Choose your booking option</h1>
        <p className="text-sm text-gray-500 mb-5">
          Select a fare type. Prices shown are per person for the entire trip.
        </p>

        {/* Fare columns */}
        <div className={`grid ${gridCols} gap-4 mb-6`}>
          {config.tiers.map((tier, i) => {
            const isSelected = selected === i;
            const price = tierPrices[i];
            const priceDiff = price - lowestPrice;

            return (
              <button
                key={tier.key}
                onClick={() => setSelectedIndex(i)}
                className={`rounded-xl border-2 text-left transition-all cursor-pointer ${
                  tier.isUpgrade ? 'bg-amber-50/50' : 'bg-white'
                } ${
                  isSelected
                    ? 'border-[#1a73e8] shadow-md'
                    : tier.isUpgrade
                      ? 'border-amber-200 hover:border-amber-300 hover:shadow-sm'
                      : 'border-gray-200 hover:border-gray-300 hover:shadow-sm'
                }`}
              >
                {/* Upgrade badge */}
                {tier.isUpgrade && (
                  <div className="px-5 pt-3 pb-0">
                    <span className="inline-block rounded-full bg-amber-100 px-2.5 py-0.5 text-[11px] font-semibold text-amber-700 uppercase tracking-wide">
                      Upgrade
                    </span>
                  </div>
                )}

                {/* Tier header */}
                <div className={`px-5 ${tier.isUpgrade ? 'pt-2' : 'pt-5'} pb-4 border-b ${isSelected ? 'border-blue-100' : tier.isUpgrade ? 'border-amber-100' : 'border-gray-100'}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <div className={`h-4 w-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                      isSelected ? 'border-[#1a73e8]' : 'border-gray-300'
                    }`}>
                      {isSelected && <div className="h-2 w-2 rounded-full bg-[#1a73e8]" />}
                    </div>
                    <span className="text-sm font-semibold text-gray-900">{tier.label}</span>
                  </div>
                  <div className="ml-6">
                    <div className="text-xl font-semibold text-gray-900">{formatPrice(price)}</div>
                    {priceDiff > 0 && (
                      <div className="text-xs text-gray-400 mt-0.5">+{formatPrice(priceDiff)}</div>
                    )}
                    <div className="text-xs text-gray-500 mt-1">{tier.description}</div>
                  </div>
                </div>

                {/* Features list */}
                <div className="px-5 py-4 space-y-3">
                  {tier.features.slice(0, config.featureCount).map((feature, fi) => (
                    <div key={fi} className="flex items-center gap-2.5">
                      <div className="flex-shrink-0 w-5 flex items-center justify-center">
                        <FeatureStatusIcon status={feature.status} />
                      </div>
                      <span className={`text-sm ${feature.status === 'none' ? 'text-gray-400' : 'text-gray-700'}`}>
                        {feature.label}
                        {feature.status === 'paid' && <span className="text-xs text-gray-400 ml-1">· Fee</span>}
                      </span>
                    </div>
                  ))}
                </div>
              </button>
            );
          })}
        </div>

        {/* Bottom bar */}
        <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-6 py-4">
          <div>
            <div className="text-sm text-gray-500">
              {selectedTier.label} &middot; {isMultiCity ? 'Multi-city' : returnFlight ? 'Round trip' : 'One way'}
            </div>
            <div className="text-xl font-semibold text-gray-900">
              {formatPrice(tierPrices[selected])}
            </div>
          </div>
          <button
            onClick={handleContinue}
            className="rounded-full bg-[#1a73e8] px-8 py-2.5 text-sm font-medium text-white hover:bg-[#1557b0] cursor-pointer transition-colors"
          >
            Continue to booking
          </button>
        </div>
      </div>
    </div>
  );
}
