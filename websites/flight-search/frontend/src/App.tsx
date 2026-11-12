import { useEffect, useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { getConfig, getGeolocation } from './api/client';
import { setBenchmarkDate } from './utils/date';
import type { GeolocationResponse } from './api/types';
import Header from './components/shared/Header';
import PasskeyGate from './components/shared/PasskeyGate';
import { CurrencyProvider } from './contexts/CurrencyContext';
import SearchPage from './pages/SearchPage';
import ResultsPage from './pages/ResultsPage';
import BookingOptionsPage from './pages/BookingOptionsPage';
import BookingPage from './pages/BookingPage';
import ConfirmationPage from './pages/ConfirmationPage';

export default function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [geo, setGeo] = useState<GeolocationResponse | null>(null);

  useEffect(() => {
    fetch('/api/auth/check')
      .then((res) => setAuthenticated(res.ok))
      .catch(() => setAuthenticated(false));
  }, []);

  // Fetch config and geolocation after auth succeeds
  useEffect(() => {
    if (authenticated) {
      getConfig()
        .then((cfg) => { if (cfg.benchmark_mode) setBenchmarkDate(cfg.benchmark_date); })
        .catch(() => {});
      getGeolocation().then(setGeo).catch(() => {});
    }
  }, [authenticated]);

  // Still checking auth status
  if (authenticated === null) {
    return null;
  }

  if (!authenticated) {
    return <PasskeyGate onAuthenticated={() => setAuthenticated(true)} />;
  }

  return (
    <CurrencyProvider defaultCurrency={geo?.currency}>
      <BrowserRouter>
        <Header />
        <Routes>
          <Route path="/" element={<SearchPage geo={geo} />} />
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/booking-options" element={<BookingOptionsPage />} />
          <Route path="/booking" element={<BookingPage />} />
          <Route path="/confirmation" element={<ConfirmationPage />} />
        </Routes>
      </BrowserRouter>
    </CurrencyProvider>
  );
}
