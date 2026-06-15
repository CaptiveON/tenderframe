"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { setAuth } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "register") {
        await api.register(email, password);
      }
      const tok = await api.login(email, password);
      setAuth(tok.access_token, email);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function guest() {
    setError(null);
    setBusy(true);
    try {
      const tok = await api.anonymous();
      setAuth(tok.access_token, "Guest");
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h1 className="text-lg font-semibold mb-1">
          {mode === "login" ? "Sign in" : "Create an account"}
        </h1>
        <p className="text-sm text-slate-500 mb-5">
          Navigate official HMRC VAT guidance with proof.
        </p>

        <form onSubmit={submit} className="space-y-3">
          <input
            type="email"
            required
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
          <input
            type="password"
            required
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-md bg-slate-900 text-white py-2 text-sm font-medium hover:bg-slate-800 disabled:opacity-50"
          >
            {busy ? "…" : mode === "login" ? "Sign in" : "Register & sign in"}
          </button>
        </form>

        <div className="mt-4 flex items-center justify-between text-sm">
          <button
            onClick={() => setMode(mode === "login" ? "register" : "login")}
            className="text-emerald-700 hover:underline"
          >
            {mode === "login" ? "Create an account" : "Have an account? Sign in"}
          </button>
          <button onClick={guest} disabled={busy} className="text-slate-500 hover:text-slate-800">
            Continue as guest
          </button>
        </div>
      </div>
    </div>
  );
}
