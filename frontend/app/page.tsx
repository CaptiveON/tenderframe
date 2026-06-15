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

export default function ChatPage() {
  const { token, ready } = useAuth();
  const router = useRouter();

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [vatMode, setVatMode] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

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
      const res = await api.sendMessage(token, content, sessionId, vatMode ? "vat" : null);
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
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-400">
              <p className="text-sm">Ask about UK VAT — registration, schemes, rates, input tax, returns, MTD.</p>
              <p className="text-xs mt-1">Every answer is cited to official GOV.UK guidance.</p>
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
                  <div
                    className={`rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                      t.abstained
                        ? "bg-amber-50 border border-amber-200 text-amber-900"
                        : "bg-slate-100 text-slate-800"
                    }`}
                  >
                    {t.abstained && (
                      <span className="block mb-1 text-xs font-semibold text-amber-700">
                        ⚠ Abstained — outside indexed guidance
                      </span>
                    )}
                    <div>{t.bot.content}</div>
                  </div>
                  {t.citations.length > 0 && <Sources citations={t.citations} />}
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
          {busy && <p className="text-sm text-slate-400">Thinking…</p>}
          <div ref={endRef} />
        </div>

        {error && <p className="px-4 pb-1 text-sm text-red-600">{error}</p>}

        <form onSubmit={send} className="border-t border-slate-200 p-3 flex items-center gap-2">
          <label className="flex items-center gap-1 text-xs text-slate-500 select-none">
            <input
              type="checkbox"
              checked={vatMode}
              onChange={(e) => setVatMode(e.target.checked)}
            />
            VAT
          </label>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={vatMode ? "Ask a UK VAT question…" : "Echo mode (no RAG)…"}
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

function Sources({ citations }: { citations: Citation[] }) {
  // de-duplicate by web_url for a clean source list
  const seen = new Set<string>();
  const unique = citations.filter((c) => {
    const key = c.web_url || c.chunk_id;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-2">
      <p className="text-xs font-semibold text-slate-500 mb-1">Sources</p>
      <ul className="space-y-1">
        {unique.map((c, i) => (
          <li key={i} className="text-xs flex items-start gap-1">
            <span className="text-emerald-600" title="verifier-passed">✓</span>
            {c.web_url ? (
              <a
                href={c.web_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-emerald-700 hover:underline"
              >
                {c.title || c.chunk_id}
                {c.section_id ? ` · ${c.section_id}` : ""}
              </a>
            ) : (
              <span>{c.chunk_id}</span>
            )}
            {c.public_updated_at && (
              <span className="text-slate-400">
                · updated {c.public_updated_at.slice(0, 10)}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
