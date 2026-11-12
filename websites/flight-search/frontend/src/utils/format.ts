export function formatPrice(usd: number): string {
  return `$${Math.round(usd).toLocaleString()}`;
}

export function formatDuration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

export function formatTime(isoString: string): string {
  // Extract HH:MM directly from ISO string to preserve the airport's
  // local timezone. new Date() would convert to the browser's timezone.
  const match = isoString.match(/T(\d{2}):(\d{2})/);
  if (!match) {
    return isoString;
  }
  const hours = parseInt(match[1], 10);
  const minutes = match[2];
  const ampm = hours >= 12 ? 'PM' : 'AM';
  const displayHour = hours % 12 || 12;
  return `${displayHour}:${minutes} ${ampm}`;
}

/** Minutes since midnight extracted from ISO string (airport local time). */
export function getLocalMinuteOfDay(isoString: string): number {
  const match = isoString.match(/T(\d{2}):(\d{2})/);
  if (!match) return 0;
  return parseInt(match[1], 10) * 60 + parseInt(match[2], 10);
}

/** Number of calendar days between two ISO date-times (in their local timezones). */
export function daysBetween(isoA: string, isoB: string): number {
  const dateA = isoA.split('T')[0];
  const dateB = isoB.split('T')[0];
  return Math.round(
    (new Date(dateB).getTime() - new Date(dateA).getTime()) / 86400000,
  );
}

export function formatDate(isoString: string): string {
  // Parse from the date portion of the ISO string (airport local date)
  const datePart = isoString.split('T')[0];
  const [y, m, d] = datePart.split('-').map(Number);
  const dt = new Date(y, m - 1, d); // local-date-only, no TZ conversion
  return dt.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });
}

export function formatStops(stops: number): string {
  if (stops === 0) return 'Nonstop';
  if (stops === 1) return '1 stop';
  return `${stops} stops`;
}

export function cabinClassLabel(cls: string): string {
  const labels: Record<string, string> = {
    economy: 'Economy',
    premium_economy: 'Premium Economy',
    business: 'Business',
    first: 'First',
  };
  return labels[cls] || cls;
}

export function tripTypeLabel(t: string): string {
  const labels: Record<string, string> = {
    round_trip: 'Round trip',
    one_way: 'One way',
    multi_city: 'Multi-city',
  };
  return labels[t] || t;
}
