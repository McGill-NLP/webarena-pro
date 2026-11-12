"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function SignupPageClient() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const passwordRulePassed = password.length >= 8 && /[\d\W_]/.test(password);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);

    if (!passwordRulePassed) {
      setError("Password must be at least 8 characters and include a number or special character.");
      setLoading(false);
      return;
    }
    if (password !== confirmPassword) {
      setError("Password confirmation does not match.");
      setLoading(false);
      return;
    }

    const response = await fetch("/api/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    const data = await response.json().catch(() => null);

    if (response.ok) {
      router.push("/app");
      return;
    }

    setError(data?.error ?? "Signup failed");
    setLoading(false);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-white px-6 py-12">
      <div className="w-full max-w-md rounded-xl border border-[var(--line)] bg-white p-8">
        <p className="mb-2 text-xs uppercase tracking-[0.1em] text-[var(--muted)]">Notion Sandbox</p>
        <h1 className="mb-6 text-3xl font-semibold tracking-[-0.02em]">Create account</h1>

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
              minLength={8}
              className="w-full rounded-md border border-[var(--line)] px-3 py-2 outline-none focus:border-[var(--line-strong)]"
            />
            <p className={`mt-1 text-xs ${passwordRulePassed ? "text-[#027a48]" : password.length > 0 ? "text-[#b42318]" : "text-[var(--muted)]"}`}>
              Use 8+ characters with a number or special character.
            </p>
          </div>

          <div>
            <label className="mb-1 block text-sm text-[var(--muted)]">Confirm password</label>
            <input
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              type="password"
              required
              minLength={8}
              className="w-full rounded-md border border-[var(--line)] px-3 py-2 outline-none focus:border-[var(--line-strong)]"
            />
            {confirmPassword.length > 0 && password !== confirmPassword ? (
              <p className="mt-1 text-xs text-[#b42318]">Passwords do not match.</p>
            ) : null}
          </div>

          {error ? <p className="text-sm text-[#b42318]">{error}</p> : null}

          <button
            type="submit"
            disabled={loading || !email.trim() || !password || !confirmPassword}
            className="w-full rounded-md border border-[#1f1f1f] bg-[#1f1f1f] px-3 py-2 text-sm text-white disabled:opacity-60"
          >
            {loading ? "Creating..." : "Create account"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-[var(--muted)]">
          Already have an account?{" "}
          <Link href="/login" className="text-[var(--text)] underline underline-offset-2">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
