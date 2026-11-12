import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { getCurrencyRates } from '../api/client';

interface CurrencyContextValue {
  currency: string;
  setCurrency: (c: string) => void;
  formatPrice: (usd: number) => string;
  /** Convert a display-currency amount back to USD. */
  toUsd: (displayAmount: number) => number;
  /** Current currency symbol (e.g. "C$", "€"). */
  symbol: string;
  currencies: string[];
  symbols: Record<string, string>;
}

const CurrencyContext = createContext<CurrencyContextValue>({
  currency: 'USD',
  setCurrency: () => {},
  formatPrice: (usd) => `$${Math.round(usd).toLocaleString()}`,
  toUsd: (n) => n,
  symbol: '$',
  currencies: ['USD'],
  symbols: { USD: '$' },
});

export function useCurrency() {
  return useContext(CurrencyContext);
}

export function CurrencyProvider({ children, defaultCurrency }: { children: ReactNode; defaultCurrency?: string }) {
  const [rates, setRates] = useState<Record<string, number>>({ USD: 1 });
  const [symbols, setSymbols] = useState<Record<string, string>>({ USD: '$' });
  const [currency, setCurrencyState] = useState<string>(() => {
    return localStorage.getItem('preferred_currency') || defaultCurrency || 'USD';
  });

  // Update if defaultCurrency changes (from geolocation) and no user preference saved
  useEffect(() => {
    if (defaultCurrency && !localStorage.getItem('preferred_currency')) {
      setCurrencyState(defaultCurrency);
    }
  }, [defaultCurrency]);

  useEffect(() => {
    getCurrencyRates()
      .then((data) => {
        setRates(data.rates);
        setSymbols(data.symbols);
      })
      .catch(() => {});
  }, []);

  function setCurrency(c: string) {
    setCurrencyState(c);
    localStorage.setItem('preferred_currency', c);
  }

  const rate = rates[currency] ?? 1;
  const currentSymbol = symbols[currency] ?? currency;

  function formatPrice(usd: number): string {
    const converted = Math.round(usd * rate);
    return `${currentSymbol}${converted.toLocaleString()}`;
  }

  function toUsd(displayAmount: number): number {
    return displayAmount / rate;
  }

  const currencies = Object.keys(rates).sort();

  return (
    <CurrencyContext.Provider value={{ currency, setCurrency, formatPrice, toUsd, symbol: currentSymbol, currencies, symbols }}>
      {children}
    </CurrencyContext.Provider>
  );
}
