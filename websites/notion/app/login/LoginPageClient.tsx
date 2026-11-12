"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const LINKED_ACCOUNTS_KEY = "accounts:linked";

export default function LoginPageClient() {
  const router = useRouter();
  const [email, setEmail] = useState("demo@webarena.local");
  const [password, setPassword] = useState("password123");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [addAccountMode, setAddAccountMode] = useState(false);
  const [returnTo, setReturnTo] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setAddAccountMode(params.get("addAccount") === "1");
    setReturnTo(params.get("returnTo"));
  }, []);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    const data = await response.json().catch(() => null);

    if (response.ok) {
      if (addAccountMode && data?.user?.id) {
        try {
          const raw = window.localStorage.getItem(LINKED_ACCOUNTS_KEY);
          const parsed = raw ? JSON.parse(raw) : [];
          const current = Array.isArray(parsed) ? parsed.map((item) => String(item)) : [];
          const next = Array.from(new Set([...current, String(data.user.id)]));
          window.localStorage.setItem(LINKED_ACCOUNTS_KEY, JSON.stringify(next));
        } catch {}
      }
      const safeReturnTo = returnTo && returnTo.startsWith("/") ? returnTo : "/app";
      router.push(safeReturnTo);
      return;
    }

    setError(data?.error ?? "Login failed");
    setLoading(false);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-white px-6 py-12">
      <div className="w-full max-w-md rounded-xl border border-[var(--line)] bg-white p-8">
        <p className="mb-2 text-xs uppercase tracking-[0.1em] text-[var(--muted)]">Notion Sandbox</p>
        <h1 className="mb-2 text-3xl font-semibold tracking-[-0.02em]">{addAccountMode ? "Add account" : "Sign in"}</h1>
        <p className="mb-6 text-sm text-[var(--muted)]">
          {addAccountMode ? "Sign in to add another account." : "Sign in to continue."}
        </p>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="mb-1 block text-sm text-[var(--muted)]">Email</label>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              required
              className="w-full rounded-md border border-[var(--line)] px-3 py-2 outline-none focus:border-[var(--line-strong)]"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-[var(--muted)]">Password</label>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              required
              className="w-full rounded-md border border-[var(--line)] px-3 py-2 outline-none focus:border-[var(--line-strong)]"
            />
          </div>

          {error ? <p className="text-sm text-[#b42318]">{error}</p> : null}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md border border-[#1f1f1f] bg-[#1f1f1f] px-3 py-2 text-sm text-white disabled:opacity-60"
          >
            {loading ? "Signing in..." : "Enter workspace"}
          </button>
        </form>

        <div className="mt-6 rounded-md border border-[var(--line)] bg-[#fafafa] p-3 text-xs text-[var(--muted)]">
          <p className="font-medium text-[#111]">Seed credentials</p>
          <p>Email: demo@webarena.local</p>
          <p>Password: password123</p>
        </div>

        <p className="mt-4 text-center text-sm text-[var(--muted)]">
          New to the website?{" "}
          <Link href="/signup" className="text-[var(--text)] underline underline-offset-2">
            Make an account
          </Link>
        </p>
      </div>
    </div>
  );
}
