/** When set, all "now" references use this fixed date instead of Date.now(). */
let _benchmarkDate: string | null = null;

export function setBenchmarkDate(isoDate: string | null): void {
  _benchmarkDate = isoDate;
}

export function getNow(): Date {
  return _benchmarkDate ? new Date(_benchmarkDate + 'T00:00:00') : new Date();
}

export function toDateString(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function addDays(d: Date, n: number): Date {
  const result = new Date(d);
  result.setDate(result.getDate() + n);
  return result;
}

export function getDefaultDepartureDate(): string {
  return toDateString(addDays(getNow(), 14));
}

export function getDefaultReturnDate(): string {
  return toDateString(addDays(getNow(), 21));
}

export function getMinBookingDate(): string {
  return toDateString(getNow());
}

export function getMaxBookingDate(): string {
  const d = getNow();
  d.setMonth(d.getMonth() + 12);
  return toDateString(d);
}

export function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

export function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month - 1, 1).getDay();
}

export function formatMonthYear(year: number, month: number): string {
  return new Date(year, month - 1).toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
  });
}
