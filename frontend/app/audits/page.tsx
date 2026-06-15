"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuditSummary } from "@/lib/types";

export default function AuditsPage() {
  const { token, ready } = useAuth();
  const router = useRouter();
  const [rows, setRows] = useState<AuditSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
              {rows.map((r) => (
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
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
