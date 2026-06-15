# ARCHITECTURE NOTES — Phase 0 audit (M0)

Brief version audited: Python/FastAPI rewrite of BRIEF.md (pgvector decision
record in appendix). Audit date: 2026-06-10. Status: **audit only — nothing
built.** Stops here for review per M0.

---

## 1. Current structure (audited facts)

- **Runtime:** Python 3.12.1 (`venv_tenderframe`), FastAPI 0.104, Uvicorn,
  **synchronous** SQLAlchemy 2.0 (`sessionmaker`, sync `def` endpoints,
  `psycopg2`). Per the brief's rule ("async throughout *if* the existing app is
  async; do not mix styles") → **new code is sync**. See risk R7 for the one
  place the brief text conflicts with this.
- **Entry point:** [backend/main.py](../backend/main.py) — app factory-less
  module, CORS for `localhost:3000`, routers mounted under `/api/v1`, global
  `AppException` handler.
- **Layering convention** (new code must match): router → service singleton →
  crud module → SQLAlchemy model, with pydantic schemas at the seams and
  `AppException` subclasses for errors. No logging framework is in use (only a
  stray `print`); structured logging arrives with the new modules (12-factor
  rule) without refactoring old ones.
- **Auth:** JWT bearer (`python-jose`), `get_current_user` dependency in
  [api/deps.py](../backend/app/api/deps.py). Reused as-is for the audit
  endpoint and chat. Known auth/chat bugs (response_model mismatch, 401 typo,
  `.one()` crash, naive-UTC expiry) were **fixed earlier this session** — auth
  is integration-ready.
- **Chat service:** [services/chat_service.py](../backend/app/services/chat_service.py)
  `process_message(db, user_id, MessageCreate)` persists user + bot `Message`
  rows in a `ChatSession` and returns `ChatResponse`. The bot reply is an
  **echo stub** — there is **no LLM call and no streaming** anywhere. The echo
  line is the integration seam.
- **Config:** `pydantic-settings` reading `backend/.env`
  ([core/config.py](../backend/app/core/config.py)). Already declared:
  `DATABASE_URL`, JWT settings, `OPENAI_*` (4 keys), `PINECONE_*` (3 keys).
  See [[rag-config-env-vars]]. **`OPENAI_API_KEY` is currently empty** (R2).
- **Migrations: none.** Tables come from `Base.metadata.create_all` on import
  in [models/__init__.py](../backend/app/models/__init__.py). Brief sanctions
  creating Alembic — we will (R5).
- **Databases (two; see [[shared-db-rag-schema]]):**
  - `tenderframe_dev` (← `DATABASE_URL` points here): clean, isolated; only
    `users`, `chat_sessions`, `messages`. **Target for all new schema.**
  - `elegantbot`: legacy/teammate schema **with data** — do not touch (§2).
- **pgvector: NOT installed and NOT in `pg_available_extensions`** on the
  local Postgres (localhost:5432). **Docker is not installed either**, which
  blocks the brief's M1 "docker-compose for local dev" as-is (R1 — decision
  needed).
- **Missing libraries** (to add to requirements.txt at M1): `pgvector`,
  `alembic`, `beautifulsoup4`, `lxml`, `httpx`, `openai`, `apscheduler`.

## 2. Inventory of previously built RAG/ingestion code

| Artifact | What it is | Verdict |
|---|---|---|
| `elegantbot` DB schema + data | Earlier RAG attempt: `source_documents`, `document_chunks` (45 rows, `pinecone_id`/`embedding_model` columns), `chunk_references`, `ingestion_logs`, `query_audit_logs`, and `structured_*` extraction tables incl. **`structured_thresholds` + `threshold_values` columns** | **DEPRECATED, untouched.** Its per-chunk threshold/structured extraction is exactly what the new brief forbids ("NO per-chunk threshold component type; hard numbers live ONLY in the curated `facts` table"). Its ingestion *code* is not in this repo (data only — nothing to build on even if we wanted to). Not deleted without approval. |
| Pinecone env keys + `Settings.PINECONE_*` | Config for the legacy vector store | **Deprecated** per the brief's decision record (pgvector is final). Left in place, unused; removable later with approval. |
| [docs/ingest.js](ingest.js) | Original Node/cheerio walker | **Deprecated** — superseded by the Python port. Keep as reference. |
| [docs/ingest.py](ingest.py) | **PROVIDED** Python port: schema adapters (`manual_section`/`answer`/`detailed_guide`/`guide`), BeautifulSoup+lxml govspeak DOM walker, semantic-class block typing, table→markdown, ≤1800-char chunk assembly, full metadata envelope, CLI + `--file` cached mode | **The starting point.** Audited: complies with the no-regex hard rule (only trivial label equality `"example"/"examples"` and a `\|`→`/` cell escape). Will be **moved** to `backend/app/ingest/ingest.py` and extended (DB wiring), CLI kept working, not rewritten. |

## 3. Where the new packages live

Adapted to repo conventions (everything under `backend/`, run from `backend/`):

```
backend/
  alembic/ + alembic.ini          # NEW — versions/0001: extension + 5 tables (brief DDL)
  app/
    core/config.py                # extend Settings: EMBEDDING_DIM, RETRIEVAL_TOP_K=8,
                                  #   RETRIEVAL_PER_SIDE=30, ABSTAIN_SCORE_THRESHOLD,
                                  #   RERANKER_ENABLED=False, HYDRATION_MAX_TOKENS=1500,
                                  #   HYDRATION_MAX_SECTIONS=6, GOVUK_FETCH_DELAY_MS=500
    models/rag.py                 # ORM for catalog/documents/chunks/facts/audit_log
    ingest/                       # NEW package
      ingest.py                   # PROVIDED file, moved here; CLI preserved
      catalog.py  fetcher.py  embedder.py
      worker.py                   # 2nd process: python -m app.ingest.worker
                                  #   [--once | --inspect <base_path>]; APScheduler daily
    rag/                          # NEW package
      vector_store.py             # VectorStore interface + PgVectorStore (sole impl)
      retrieve.py                 # hybrid top-30+30 → RRF top-8 → sibling hydration
      answer.py  verify.py  audit.py
      schemas.py                  # pydantic seam models (RetrievedContext, Citation, …)
    services/rag_service.py       # orchestrates retrieve→answer→verify→audit
    api/v1/answers.py             # GET /api/v1/answers/{id}/audit (get_current_user)
  eval/golden.json  eval/run.py   # 30 golden Qs + report script
```

Process topology (modular monolith, two deployables, one DB):
`uvicorn main:app` (api) and `python -m app.ingest.worker` (ingest-worker).
Boundaries are function/class interfaces with pydantic models — no HTTP
between packages.

## 4. How the RAG pipeline hooks into the chat flow

**Phase 0 decision (the brief asks us to choose): `mode: 'vat'` flag on the
existing message endpoint** — not a dedicated router. Rationale: reuses
session/message persistence, auth, and the `ChatResponse` contract; the
domain is data (`mode` value = domain label), matching domain-as-config.

1. `MessageCreate` gains `mode: Optional[str] = None`
   ([schema/chat.py](../backend/app/schema/chat.py)).
2. `chat_service.process_message`: if `mode` names a known domain →
   `rag_service.answer_question(db, user, session, question, domain)`
   (retrieve → hydrate → answer → verify → audit); else → current echo path,
   unchanged.
3. The bot `Message` is persisted as today; `ChatResponse` gains
   `citations: list[Citation] = []` and `abstained: bool = False`
   (machine-readable for the future frontend). Every answer ends with the
   one-line "official-guidance navigation, not professional advice" notice.
4. `audit.py` writes the append-only `audit_log` row with `matched` and
   `hydrated` recorded **separately**; `conversation_id` = `chat_sessions.id`.
5. `GET /api/v1/answers/{id}/audit` returns the full rendered trail.

Provider mapping (the repo "already calls" no LLM — the de-facto provider per
existing env keys is **OpenAI**, R8): small model = `OPENAI_CLASSIFICATION_MODEL`
(routing + verify), strong = `OPENAI_GENERATION_MODEL` (final answer),
embeddings = `OPENAI_EMBEDDING_MODEL` with `EMBEDDING_DIM` in settings
(default `text-embedding-3-small` / 1536).

Retrieval/hydration follow the brief's core design verbatim: every chunk type
embedded; answer unit = section via `(document_id, heading_path, chunk_index)`
sibling query; hydration budget from settings; trim priority matched chunk →
sibling examples → sibling tables → remaining text; filter
`superseded_at IS NULL`; RRF in SQL + small Python merge.

## 5. Risks & decisions needed before M1

- **R1 — local pgvector (BLOCKER, needs your choice).** pgvector is not
  installed and not available on your local Postgres; Docker is not installed
  either, so the brief's M1 "docker-compose for local dev" cannot run today.
  Options: **(a)** `brew install pgvector` onto your existing Postgres
  (fastest; keeps `tenderframe_dev`), or **(b)** install Docker Desktop and
  run the compose file the brief expects. Recommend **(a)** locally and
  writing the compose file anyway for M6 parity.
- **R2 — `OPENAI_API_KEY` is empty** in `backend/.env`. M1's gate requires
  example chunks to **have embeddings**, so a real key is needed by M1.
- **R3 — approval to touch existing chat code (minimal, additive).** Per
  Phase 0 rule 4, the only changes to existing files: `MessageCreate.mode`,
  `ChatResponse.citations/abstained`, the one branch in
  `chat_service.process_message`, and new Settings fields. No refactors.
  **Explicit approval requested.**
- **R4 — embedding dimension is frozen at migration time** (`vector(1536)`
  for `text-embedding-3-small`). Changing models later = column alter +
  re-embed. Confirm 1536 before the Alembic migration is written.
- **R5 — Alembic is new to this repo.** It will own only the 5 new tables;
  existing `users`/`chat_sessions`/`messages` stay on `create_all` for now to
  avoid refactoring working code (can be stamped into Alembic later).
- **R6 — legacy remnants left in place.** `elegantbot` data, Pinecone keys,
  `docs/ingest.js`: deprecated, untouched, not built upon (per brief §Phase 0.2).
- **R7 — minor brief-internal conflict, resolved per its own rule.** Component
  spec says fetcher is "httpx, **async**", but the locked runtime rule says
  match the existing app's style, which is **sync** — and the fetcher is
  required to be *sequential with 500ms delays*, so async buys nothing. New
  code is sync (`httpx` sync client). Flagging rather than silently choosing.
- **R8 — provider.** "Use whatever provider the repo already calls for chat"
  — it calls none. De-facto answer is OpenAI (keys already in env/Settings).
  Confirm.

## 6. What M1 will deliver (once R1–R4 are answered)

pgvector available locally → Alembic init + migration 0001 (brief DDL,
`vector(EMBEDDING_DIM)`) → move `docs/ingest.py` to `app/ingest/ingest.py`,
wire output to `documents`/`chunks` (version-hash supersession) → embedder →
worker `--once` / `--inspect` → ingest VATREG29550 + one multi-part guide →
your gate: `--inspect` shows example blocks as `chunk_type='example'` **with
embeddings**, guide parts as separate chunks with part metadata.

**STOP — M0 complete. Awaiting review and answers to R1 (a/b), R2, R3, R4, R8.**
