import type { FlightOffer } from '../api/types';

/** Check if two flights share at least one carrier. */
export function sharesAirline(a: FlightOffer, b: FlightOffer): boolean {
  const airlinesA = new Set(a.segments.map(s => s.airline_code));
  return b.segments.some(s => airlinesA.has(s.airline_code));
}

/** Return the effective price of a return flight given the selected outbound. */
export function effectiveReturnPrice(
  ret: FlightOffer,
  outbound: FlightOffer,
  discountRate: number,
): number {
  if (sharesAirline(ret, outbound)) {
    return Math.round(ret.price_usd * discountRate);
  }
  return ret.price_usd;
}

/** Total round-trip price for an outbound + return pair. */
export function roundTripTotal(
  outbound: FlightOffer,
  ret: FlightOffer,
  discountRate: number,
): number {
  return outbound.price_usd + effectiveReturnPrice(ret, outbound, discountRate);
}

/** Minimum round-trip price for a given outbound across all returns. */
export function minRoundTripPrice(
  outbound: FlightOffer,
  allReturns: FlightOffer[],
  discountRate: number,
): number | null {
  if (allReturns.length === 0) return null;
  let min = Infinity;
  for (const ret of allReturns) {
    const total = roundTripTotal(outbound, ret, discountRate);
    if (total < min) min = total;
  }
  return min;
}
