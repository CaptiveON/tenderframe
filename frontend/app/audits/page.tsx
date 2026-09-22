"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuditSummary } from "@/lib/types";

type Filter = "all" | "answered" | "abstained";

export default function AuditsPage() {
  const { token, ready } = useAuth();
  const router = useRouter();
  const [rows, setRows] = useState<AuditSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");

  useEffect(() => {
    if (ready && !token) router.replace("/login");
  }, [ready, token, router]);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      setRows(await api.audits(token));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load audits");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  if (!ready || !token) return null;

  const counts = {
    all: rows.length,
    answered: rows.filter((r) => !r.abstained).length,
    abstained: rows.filter((r) => r.abstained).length,
  };
  const shown = rows.filter(
    (r) =>
      (filter === "all" || (filter === "abstained") === r.abstained) &&
      r.question.toLowerCase().includes(q.trim().toLowerCase()),
  );

  return (
    <div className="flex-1 mx-auto w-full max-w-5xl p-4">
      <h1 className="text-lg font-semibold mb-1">Audit log</h1>
      <p className="text-sm text-slate-500 mb-4">
        Every answer is recorded — question, retrieved context, citations, and per-claim verification.
      </p>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {loading && <p className="text-sm text-slate-400">Loading…</p>}

      {!loading && rows.length === 0 && (
        <p className="text-sm text-slate-400">
          No audited answers yet. Ask a question in the{" "}
          <Link href="/" className="text-emerald-700 hover:underline">chat</Link>.
        </p>
      )}

      {rows.length > 0 && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-md border border-slate-200 bg-white p-0.5 text-xs">
              {(["all", "answered", "abstained"] as Filter[]).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`rounded px-3 py-1.5 capitalize ${
                    filter === f ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {f} <span className={filter === f ? "text-slate-300" : "text-slate-400"}>{counts[f]}</span>
                </button>
              ))}
            </div>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search questions…"
              className="ml-auto w-64 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-left text-xs uppercase">
                <tr>
                  <th className="px-4 py-2 font-medium">#</th>
                  <th className="px-4 py-2 font-medium">Question</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Cites</th>
                  <th className="px-4 py-2 font-medium">When</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {shown.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => router.push(`/audits/${r.id}`)}
                    className="cursor-pointer hover:bg-slate-50"
                  >
                    <td className="px-4 py-2 text-slate-400">{r.id}</td>
                    <td className="px-4 py-2 max-w-md truncate">{r.question}</td>
                    <td className="px-4 py-2">
                      {r.abstained ? (
                        <span className="text-amber-700 text-xs font-medium">abstained</span>
                      ) : (
                        <span className="text-emerald-700 text-xs font-medium">answered</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-slate-500">{r.n_citations}</td>
                    <td className="px-4 py-2 text-slate-400 text-xs">{r.created_at.slice(0, 16)}</td>
                  </tr>
                ))}
                {shown.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-6 text-center text-slate-400 text-sm">
                      No answers match.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
