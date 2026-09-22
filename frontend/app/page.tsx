"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { ChatSession, Citation, Message } from "@/lib/types";

interface Turn {
  user: Message;
  bot: Message;
  citations: Citation[];
  abstained: boolean;
  auditId: number | null;
}

const SUGGESTED = [
  "Do I need to register for VAT? My turnover hit £92,000 this year.",
  "Can I reclaim the VAT on a car I bought for my business?",
  "Am I eligible for the Flat Rate Scheme, and what are the limits to join and leave?",
  "Is there a discount on the flat rate in my first year of registration?",
];

export default function ChatPage() {
  const { token, ready } = useAuth();
  const router = useRouter();

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ready && !token) router.replace("/login");
  }, [ready, token, router]);

  const loadSessions = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.sessions(token);
      setSessions(data.chat_sessions);
    } catch {
      /* ignore sidebar load errors */
    }
  }, [token]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function openSession(id: string) {
    if (!token) return;
    setSessionId(id);
    setError(null);
    try {
      const hist = await api.history(token, id);
      // pair consecutive user/bot messages into turns (citations only live on fresh replies)
      const paired: Turn[] = [];
      for (let i = 0; i < hist.messages.length; i++) {
        const m = hist.messages[i];
        if (m.role === "user") {
          const next = hist.messages[i + 1];
          if (next && next.role === "bot") {
            paired.push({ user: m, bot: next, citations: [], abstained: false, auditId: null });
            i++;
          }
        }
      }
      setTurns(paired);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load history");
    }
  }

  function newChat() {
    setSessionId(null);
    setTurns([]);
    setError(null);
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!token || !input.trim() || busy) return;
    const content = input.trim();
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const res = await api.sendMessage(token, content, sessionId, "vat");
      setSessionId(res.session_id);
      setTurns((t) => [
        ...t,
        {
          user: res.user_message,
          bot: res.bot_response,
          citations: res.citations,
          abstained: res.abstained,
          auditId: res.audit_id,
        },
      ]);
      loadSessions();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to send");
    } finally {
      setBusy(false);
    }
  }

  if (!ready || !token) return null;

  return (
    <div className="flex-1 mx-auto w-full max-w-6xl grid grid-cols-[240px_1fr] gap-4 p-4">
      {/* Sessions sidebar */}
      <aside className="bg-white rounded-xl border border-slate-200 flex flex-col overflow-hidden">
        <button
          onClick={newChat}
          className="m-2 rounded-md bg-emerald-600 text-white text-sm py-2 hover:bg-emerald-700"
        >
          + New chat
        </button>
        <p className="px-3 pt-1 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Conversations
        </p>
        <div className="overflow-y-auto flex-1">
          {sessions.length === 0 && (
            <p className="px-3 py-2 text-xs text-slate-400">No conversations yet</p>
          )}
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => openSession(s.id)}
              className={`w-full text-left px-3 py-2 text-sm truncate hover:bg-slate-100 ${
                s.id === sessionId ? "bg-slate-100 font-medium" : "text-slate-600"
              }`}
              title={s.title}
            >
              {s.title}
            </button>
          ))}
        </div>
      </aside>

      {/* Conversation */}
      <section className="bg-white rounded-xl border border-slate-200 flex flex-col overflow-hidden h-[calc(100vh-7.5rem)]">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {turns.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <h2 className="text-xl font-semibold text-slate-800">Ask about UK VAT</h2>
              <p className="text-sm text-slate-500 mt-1 max-w-md">
                Registration, schemes, rates, input tax, returns and Making Tax Digital — every answer is
                cited to official GOV.UK guidance and checked claim by claim. If it can&apos;t prove an
                answer, it says so.
              </p>
              <div className="mt-6 grid grid-cols-2 gap-2 max-w-2xl w-full">
                {SUGGESTED.map((q) => (
                  <button
                    key={q}
                    onClick={() => {
                      setInput(q);
                      inputRef.current?.focus();
                    }}
                    className="text-left text-sm rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700 hover:border-emerald-400 hover:bg-emerald-50"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((t, i) => (
            <div key={i} className="space-y-2">
              <div className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl bg-slate-900 text-white px-4 py-2 text-sm">
                  {t.user.content}
                </div>
              </div>
              <div className="flex justify-start">
                <div className="max-w-[85%] space-y-2">
                  {t.abstained ? (
                    <div className="rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap bg-amber-50 border border-amber-200 text-amber-900">
                      <span className="block mb-1 text-xs font-semibold text-amber-700">
                        ⚠ Abstained — outside the indexed guidance
                      </span>
                      <div>{t.bot.content}</div>
                    </div>
                  ) : (
                    <Answer text={t.bot.content} citations={t.citations} />
                  )}
                  {t.auditId != null && (
                    <Link
                      href={`/audits/${t.auditId}`}
                      className="inline-block text-xs text-slate-400 hover:text-slate-700"
                    >
                      View audit trail #{t.auditId} →
                    </Link>
                  )}
                </div>
              </div>
            </div>
          ))}
          {busy && (
            <p className="text-sm text-slate-400">Retrieving guidance, drafting and verifying every claim…</p>
          )}
          <div ref={endRef} />
        </div>

        {error && <p className="px-4 pb-1 text-sm text-red-600">{error}</p>}

        <form onSubmit={send} className="border-t border-slate-200 p-3 flex items-center gap-2">
          <span className="hidden sm:inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 whitespace-nowrap">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Cited to GOV.UK
          </span>
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a UK VAT question…"
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-md bg-emerald-600 text-white px-4 py-2 text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </section>
    </div>
  );
}

/** Unique sources in first-seen order; map source key -> 1-based number. */
function indexSources(citations: Citation[]) {
  const sources: Citation[] = [];
  const index = new Map<string, number>();
  for (const c of citations) {
    const key = c.web_url || c.chunk_id;
    if (!index.has(key)) {
      sources.push(c);
      index.set(key, sources.length);
    }
  }
  return { sources, index };
}

/** Split the answer body into segments, attaching [n] markers after each cited claim. */
function annotate(body: string, citations: Citation[], index: Map<string, number>) {
  const byClaim = new Map<string, Set<number>>();
  for (const c of citations) {
    const n = index.get(c.web_url || c.chunk_id);
    if (!n) continue;
    if (!byClaim.has(c.claim)) byClaim.set(c.claim, new Set());
    byClaim.get(c.claim)!.add(n);
  }
  type Seg = { text: string; refs?: number[] };
  let segs: Seg[] = [{ text: body }];
  // longest claims first so a short claim never splits a longer one that contains it
  for (const claim of [...byClaim.keys()].sort((a, b) => b.length - a.length)) {
    const refs = [...byClaim.get(claim)!].sort((a, b) => a - b);
    const next: Seg[] = [];
    for (const s of segs) {
      const i = s.refs ? -1 : s.text.indexOf(claim);
      if (i < 0) {
        next.push(s);
        continue;
      }
      if (i > 0) next.push({ text: s.text.slice(0, i) });
      next.push({ text: claim, refs });
      const after = s.text.slice(i + claim.length);
      if (after) next.push({ text: after });
    }
    segs = next;
  }
  return segs;
}

function Answer({ text, citations }: { text: string; citations: Citation[] }) {
  // backend format: "<answer sentences>\n\n<disclaimer>"
  const cut = text.lastIndexOf("\n\n");
  const body = cut > 0 ? text.slice(0, cut) : text;
  const note = cut > 0 ? text.slice(cut + 2) : null;
  const { sources, index } = indexSources(citations);
  const segs = annotate(body, citations, index);

  return (
    <>
      <div className="rounded-2xl px-4 py-2.5 text-sm leading-relaxed bg-slate-100 text-slate-800">
        <p className="m-0">
          {segs.map((s, i) => (
            <span key={i}>
              {s.text}
              {s.refs?.map((n) => (
                <sup key={n} className="ml-0.5 text-[10px] font-semibold text-emerald-700">
                  [{n}]
                </sup>
              ))}
            </span>
          ))}
        </p>
        {note && <p className="m-0 mt-2 text-xs text-slate-500 italic">{note}</p>}
      </div>
      {sources.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-2.5">
          <p className="text-xs font-semibold text-slate-500 mb-1.5">
            Sources
            <span className="ml-2 font-normal text-slate-400">
              {sources.length} · every claim verifier-passed
            </span>
          </p>
          <ol className="space-y-1">
            {sources.map((c, i) => (
              <li key={i} className="text-xs flex items-start gap-1.5">
                <span className="font-semibold text-emerald-700 tabular-nums">[{i + 1}]</span>
                {c.web_url ? (
                  <a
                    href={c.web_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-emerald-700 hover:underline"
                  >
                    {c.title || c.chunk_id}
                    {c.section_id ? ` · ${c.section_id}` : ""}
                    {!c.section_id && c.web_url.includes("#") && (
                      <span className="text-slate-500"> — {c.web_url.split("#")[1].replace(/-/g, " ")}</span>
                    )}
                  </a>
                ) : (
                  <span>{c.chunk_id}</span>
                )}
                {c.public_updated_at && (
                  <span className="text-slate-400">· updated {c.public_updated_at.slice(0, 10)}</span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </>
  );
}
