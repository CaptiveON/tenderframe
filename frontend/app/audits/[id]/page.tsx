"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuditTrail } from "@/lib/types";

export default function AuditDetailPage() {
  const { token, ready } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const [trail, setTrail] = useState<AuditTrail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ready && !token) router.replace("/login");
  }, [ready, token, router]);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      setTrail(await api.audit(token, Number(params.id)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load");
    }
  }, [token, params.id]);

  useEffect(() => {
    load();
  }, [load]);

  if (!ready || !token) return null;

  return (
    <div className="flex-1 mx-auto w-full max-w-4xl p-4 space-y-4">
      <Link href="/audits" className="text-sm text-slate-400 hover:text-slate-700">
        ← Audit log
      </Link>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {!trail && !error && <p className="text-sm text-slate-400">Loading…</p>}

      {trail && (
        <>
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold">Audit #{trail.id}</h1>
            {trail.abstained ? (
              <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded">
                abstained
              </span>
            ) : (
              <span className="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
                answered
              </span>
            )}
            <span className="text-xs text-slate-400 ml-auto">
              {trail.model} · {trail.created_at.slice(0, 19)}
            </span>
          </div>

          <Card title="Question">
            <p className="text-sm">{trail.question}</p>
          </Card>

          <Card title="Answer">
            <p className="text-sm whitespace-pre-wrap">{trail.answer}</p>
          </Card>

          <Card title={`Citations (${trail.citations.length})`}>
            {trail.citations.length === 0 ? (
              <p className="text-xs text-slate-400">None.</p>
            ) : (
              <ul className="space-y-2">
                {trail.citations.map((c, i) => (
                  <li key={i} className="text-sm border-l-2 border-emerald-300 pl-3">
                    <div className="flex items-center gap-2">
                      <span className={c.verified ? "text-emerald-600" : "text-red-500"}>
                        {c.verified ? "✓ verified" : "✗ unverified"}
                      </span>
                      {c.source?.web_url && (
                        <a
                          href={c.source.web_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-emerald-700 hover:underline text-xs"
                        >
                          {c.source.title || c.chunk_id}
                          {c.source.section_id ? ` · ${c.source.section_id}` : ""} ↗
                        </a>
                      )}
                    </div>
                    <p className="text-slate-600 text-xs mt-0.5">“{c.claim}”</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <div className="grid grid-cols-2 gap-4">
            <Card title={`Matched (${trail.matched.length})`} subtitle="retrieval-scored">
              <ChunkList items={trail.matched.map((m) => ({ id: m.chunk_id, score: m.score }))} />
            </Card>
            <Card title={`Hydrated (${trail.hydrated.length})`} subtitle="added siblings">
              <ChunkList items={trail.hydrated.map((m) => ({ id: m.chunk_id }))} />
            </Card>
          </div>

          <Card title="Verification">
            {trail.verification.length === 0 ? (
              <p className="text-xs text-slate-400">No per-claim checks recorded.</p>
            ) : (
              <ul className="space-y-1">
                {trail.verification.map((v, i) => (
                  <li key={i} className="text-xs flex items-start gap-2">
                    {v.reason ? (
                      <span className="text-slate-500">
                        reason: {v.reason}
                        {v.best_similarity != null && ` (sim ${v.best_similarity.toFixed(3)})`}
                      </span>
                    ) : (
                      <>
                        <span className={v.verified ? "text-emerald-600" : "text-red-500"}>
                          {v.verified ? "✓" : "✗"}
                        </span>
                        <span className="text-slate-400 font-mono">{v.chunk_id}</span>
                        <span className="text-slate-600 truncate">{v.claim}</span>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-baseline gap-2 mb-2">
        <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
        {subtitle && <span className="text-xs text-slate-400">{subtitle}</span>}
      </div>
      {children}
    </div>
  );
}

function ChunkList({ items }: { items: { id: string; score?: number }[] }) {
  if (items.length === 0) return <p className="text-xs text-slate-400">None.</p>;
  return (
    <ul className="space-y-1">
      {items.map((it, i) => (
        <li key={i} className="text-xs font-mono text-slate-600 flex justify-between gap-2">
          <span className="truncate">{it.id}</span>
          {it.score != null && <span className="text-slate-400">{it.score.toFixed(4)}</span>}
        </li>
      ))}
    </ul>
  );
}
