import { useState, type FormEvent } from 'react';

interface Props {
  onAuthenticated: () => void;
}

export default function PasskeyGate({ onAuthenticated }: Props) {
  const [passkey, setPasskey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/auth/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passkey }),
      });

      if (res.ok) {
        onAuthenticated();
      } else {
        setError('Invalid passkey');
        setPasskey('');
      }
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="w-full max-w-sm mx-4">
        <div className="text-center mb-8">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" className="mx-auto mb-4 text-[#1a73e8]">
            <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" fill="currentColor"/>
          </svg>
          <h1 className="text-2xl font-medium text-gray-900">Flights</h1>
          <p className="text-sm text-gray-500 mt-1">Enter passkey to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <input
            type="password"
            value={passkey}
            onChange={(e) => setPasskey(e.target.value)}
            placeholder="Passkey"
            autoFocus
            className="w-full px-4 py-3 rounded-lg border border-gray-300 text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#1a73e8] focus:border-transparent"
          />

          {error && (
            <p className="mt-3 text-sm text-red-600">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !passkey}
            className="mt-4 w-full py-3 rounded-lg bg-[#1a73e8] text-white font-medium hover:bg-[#1557b0] disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            {loading ? 'Verifying...' : 'Continue'}
          </button>
        </form>
      </div>
    </div>
  );
}
