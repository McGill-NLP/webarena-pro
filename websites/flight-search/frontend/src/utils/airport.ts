export function extractIataFromText(text: string): string {
  const trimmed = text.trim();
  const parenthesized = trimmed.match(/\(([A-Za-z]{3})\)\s*$/);
  if (parenthesized) return parenthesized[1].toUpperCase();

  if (/^[A-Za-z]{3}$/.test(trimmed)) return trimmed.toUpperCase();

  return '';
}
