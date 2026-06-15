# BRIEF — Auditable VAT Compliance RAG (Python/FastAPI)

You are Claude Code, working inside an existing Python/FastAPI backend
repository. Read this entire brief before writing any code. All architectural
decisions in here are FINAL — do not propose alternatives unless something is
impossible, in which case stop and explain before proceeding.

## Mission

Extend the existing backend (working chat service + working auth service, no
frontend yet) into an industrial-grade, auditable UK VAT compliance assistant
for SMEs:

- Ingests UK VAT guidance from the GOV.UK Content API (structured JSON).
- Answers natural-language questions through the EXISTING chat service.
- Every factual claim in an answer carries a verifiable citation to a specific
  GOV.UK paragraph (section id + deep link + version + retrieval date).
- If retrieval is weak, the system abstains instead of guessing.
- Every Q&A is recorded in an append-only audit log, including exactly what
  context the LLM saw.

v1 scope: domestic VAT only (registration, schemes, rates, input tax,
returns, MTD). Explicitly out of scope: customs/import-export VAT,
corporation tax, PAYE. HOWEVER the pipeline must be domain-generic: future
domains (wider tax compliance, tender application help) are added by
appending catalog rows and domain labels — never by touching pipeline code.

Positioning: "navigate official HMRC guidance with proof" — NOT tax advice.
Every answer ends with a one-line notice that this is official-guidance
navigation, not professional advice.

## Build priority (strict order)

1. FIRST: data ingestion + RAG answering, fully working and testable
   locally end to end (milestones M0–M5). The user must be able to ingest
   real GOV.UK content, ask questions through the chat API, and inspect
   citations and audit trails BEFORE any deployment work begins.
2. ONLY THEN: deployment packaging for cloud (milestone M6).
3. Cloud-readiness is achieved during M0–M5 through discipline, not
   artifacts: 12-factor style — all config via environment variables,
   stateless API process, no local-disk state outside Postgres, structured
   logging, the two-process split below. Do not write cloud-provider
   manifests, CI pipelines, or IaC before M6.

## Phase 0 — MANDATORY audit of what is already built (build nothing yet)

1. Read the existing repo end to end: FastAPI app structure, routers, how
   the chat service stores conversations and streams replies, how auth
   dependencies/middleware work, which DB layer is used (SQLAlchemy? raw
   asyncpg?), async vs sync conventions, settings/env conventions, Alembic
   setup (create one if absent), and ANY previously built ingestion/RAG/
   parsing code from earlier development attempts.
2. For previously built RAG/ingestion remnants: inventory them in the notes.
   Anything based on regex content extraction or HTML page scraping is to be
   marked deprecated and left untouched (do not delete without approval; do
   not build on it either).
3. Write `docs/ARCHITECTURE_NOTES.md` summarising: current structure, what
   exists and is reusable, what is deprecated, where the new packages will
   live, how the RAG pipeline hooks into the chat message flow, and risks.
4. Do NOT refactor existing chat/auth code unless something genuinely blocks
   integration. If it does, list the minimal change in ARCHITECTURE_NOTES.md
   and get explicit user approval in chat before touching it.
5. Follow the repo's existing conventions (pydantic models, error handling,
   logging, dependency injection). New code must look like it belongs.

## Locked technical decisions

- Language/runtime: Python, matching the repo's version. FastAPI for all
  HTTP. Async throughout if the existing app is async; do not mix styles.
- Database & vectors: PostgreSQL with the `pgvector` extension. ONE Postgres
  for everything: documents, chunks, vectors, facts, audit log. This is
  final for v1 — NOT Pinecone, NOT a separate vector DB (decision record in
  the appendix; do not relitigate). Implement vector search behind a thin
  `VectorStore` interface (one class, one implementation: `PgVectorStore`)
  so a managed vector DB could be swapped later WITHOUT building a second
  implementation now.
- Service topology: MODULAR MONOLITH WITH SERVICE-SHAPED BOUNDARIES,
  prepared for cloud deployment but not split prematurely:
  - One repository, one shared `core/` (db, settings, models).
  - Two deployable processes from day one:
    1. `api` — the existing FastAPI app + new RAG routes (uvicorn).
    2. `ingest-worker` — separate entrypoint (`python -m app.ingest.worker`)
       running catalog refresh / fetch / chunk / embed on a schedule
       (APScheduler or simple asyncio loop). Shares codebase and DB but runs
       as its own process so it can be deployed, scaled, and restarted
       independently in the cloud.
  - Boundaries between `ingest/`, `rag/`, and chat are function/class
    interfaces with pydantic models at the seams — no reaching into each
    other's internals — so any boundary can later become an HTTP/queue
    boundary without rewrites.
- HTML walking: BeautifulSoup4 + lxml. The file `app/ingest/ingest.py`
  (provided, working, tested on real VATREG29550) is the starting point for
  the schema adapters and govspeak-aware DOM walker. Extend it; do not
  rewrite it from scratch.
- HARD RULE — no regex over content. Structure comes from the Content API
  JSON fields and the govspeak-rendered DOM (heading hierarchy, semantic
  classes like `example`, `call-to-action`, `info-notice`, `<table>`).
  A previous version of this project died from regex content extraction.
  The only permitted pattern matches are trivial label checks
  (e.g. heading text equals "Example") — never mining facts out of prose.
  Corollary: there is NO per-chunk "threshold" component type. Threshold
  sentences live inside ordinary text chunks; hard numbers live ONLY in the
  curated `facts` table.
- Sources: GOV.UK Content API (`https://www.gov.uk/api/content{base_path}`)
  and GOV.UK Search API (`https://www.gov.uk/api/search.json`) only, via
  httpx. No HTML page scraping. No legislation.gov.uk in v1.
- Embeddings + LLM: use whatever provider the repo already calls for chat.
  Cheap/small model for routing and verification, strong model for the
  final answer. Embedding dimension lives in settings, never hardcoded.
- Retrieval: hybrid = pgvector cosine similarity + Postgres full-text
  search (`tsvector`/`ts_rank`) merged with Reciprocal Rank Fusion, in SQL
  plus a small Python merge. No external search engine. Optional reranker
  behind a settings flag, default off in v1.
- Domain-as-config: the ONLY place "VAT" appears is the catalog table and a
  domain label. Zero domain-specific logic in pipeline code.

## Retrieval unit vs answer unit (hydration) — core design

Two distinct concepts. Do not conflate them.

- RETRIEVAL UNIT = the chunk. EVERY chunk is embedded and searchable,
  regardless of chunk_type — text, example, table, action, notice. Examples
  and tables are often the best semantic match for scenario-phrased SME
  questions and rate questions; excluding them from the index is forbidden.
- ANSWER UNIT = the section. When a chunk matches, hydrate its SIBLINGS —
  chunks from the same document sharing the same top-level heading path —
  and feed the assembled section to the LLM in document order. No separate
  components table: the sibling relationship is already encoded by
  (document_id, heading_path, chunk_index). Hydration is one SQL query.
- HYDRATION BUDGET (settings, with these defaults): max ~1,500 tokens of
  hydrated context per matched section, max 6 sections per answer.
  Priority order when trimming: matched chunk first, then sibling examples,
  then sibling tables, then remaining sibling text. More context is not
  monotonically better; respect the budget.
- AUDIT SPLIT: the audit log records `matched` (chunks retrieval scored)
  and `hydrated` (additional sibling chunks the LLM saw) as separate
  arrays. The citation contract applies to EVERYTHING in context: the model
  may cite hydrated chunks, and the verifier checks those citations exactly
  like matched ones.

## Data model (Alembic migration; adapt naming to repo conventions)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- what to ingest; seeded for VAT, rows added for future domains
CREATE TABLE catalog (
  base_path     text PRIMARY KEY,
  domain        text NOT NULL,            -- 'vat'
  source_kind   text NOT NULL,            -- 'manual_section' | 'guide' | 'answer' | 'detailed_guide'
  enabled       boolean NOT NULL DEFAULT true,
  added_at      timestamptz NOT NULL DEFAULT now()
);

-- one row per (base_path, version); never delete, only supersede
CREATE TABLE documents (
  id                bigserial PRIMARY KEY,
  base_path         text NOT NULL,
  content_id        text,
  schema_name       text NOT NULL,
  title             text NOT NULL,
  description       text,
  section_id        text,                 -- e.g. VATREG29550
  public_updated_at timestamptz,
  version_hash      text NOT NULL,        -- sha256 of details body
  raw_json          jsonb NOT NULL,       -- full ContentItem, the audit source of truth
  retrieved_at      timestamptz NOT NULL DEFAULT now(),
  superseded_at     timestamptz,          -- null = current version
  UNIQUE (base_path, version_hash)
);

CREATE TABLE chunks (
  id            bigserial PRIMARY KEY,
  document_id   bigint NOT NULL REFERENCES documents(id),
  chunk_id      text NOT NULL,            -- '/path#part:idx' as in ingest.py
  domain        text NOT NULL,
  chunk_type    text NOT NULL,            -- text | example | table | action | notice
  heading_path  text[] NOT NULL DEFAULT '{}',
  chunk_index   int  NOT NULL,            -- document order, for sibling hydration
  anchor        text,
  text          text NOT NULL,
  tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  embedding     vector(/* dim from settings */),  -- populated for EVERY chunk_type
  metadata      jsonb NOT NULL,           -- full envelope from ingest.py
  UNIQUE (chunk_id, document_id)
);
CREATE INDEX ON chunks USING gin(tsv);
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON chunks (domain);
CREATE INDEX ON chunks (document_id, chunk_index);

-- curated hard numbers; LLM-proposed at ingestion, human-approved before use
CREATE TABLE facts (
  key             text NOT NULL,          -- 'vat.registration_threshold'
  value           text NOT NULL,
  effective_from  date NOT NULL,
  effective_to    date,
  source_chunk_id text NOT NULL,
  approved        boolean NOT NULL DEFAULT false,
  PRIMARY KEY (key, effective_from)
);

-- append-only; the app never issues UPDATE or DELETE against this table
CREATE TABLE audit_log (
  id              bigserial PRIMARY KEY,
  user_id         text NOT NULL,
  conversation_id text NOT NULL,
  question        text NOT NULL,
  domain          text,
  matched         jsonb NOT NULL,         -- [{chunk_id, document_id, version_hash, score}]
  hydrated        jsonb NOT NULL,         -- [{chunk_id, document_id, version_hash}]
  answer          text NOT NULL,
  citations       jsonb NOT NULL,         -- [{claim, chunk_id, verified}]
  verification    jsonb NOT NULL,         -- per-claim entailment results
  abstained       boolean NOT NULL DEFAULT false,
  model           text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);
```

## Components to build (package layout — adapt to repo conventions)

1. `app/ingest/catalog.py` — builds/refreshes the VAT catalog via the
   Search API (filter by HMRC organisation + relevant document types + VAT
   terms) plus recursive walk of `child_section_groups` from VAT manual
   roots (start set: vat-registration-manual, vat-input-tax,
   vat-supply-and-consideration, flat rate scheme guidance, the
   /vat-registration guide, VAT notices published as guidance pages).
   Writes rows to `catalog`.
2. `app/ingest/fetcher.py` — for each enabled catalog row, GET the Content
   API (httpx, async), compare body hash to current
   `documents.version_hash`; if changed, insert new document version, mark
   old `superseded_at`, re-chunk, re-embed. Sequential with ~500ms delay
   between requests (be polite), retry with exponential backoff.
3. `app/ingest/ingest.py` — PROVIDED. Schema adapters + DOM walker + chunk
   assembly + metadata envelope. Wire its output into the DB instead of
   chunks.json. Keep its CLI mode working for debugging.
4. `app/ingest/embedder.py` — batch-embeds ALL new chunks (every
   chunk_type), fills `chunks.embedding`.
5. `app/ingest/worker.py` — the second process: runs catalog refresh +
   fetcher on a schedule (daily) and on demand
   (`python -m app.ingest.worker --once`), plus
   `--inspect <base_path>` pretty-printer for chunk review.
6. `app/rag/retrieve.py` — input: question + domain. Hybrid search over all
   chunks (top 30 each side), RRF merge to top 8 matched chunks, then
   sibling hydration per the budget. Filter to documents where
   `superseded_at IS NULL`. Returns {matched, hydrated, assembled_context}.
   Implemented behind the `VectorStore` interface.
7. `app/rag/answer.py` — composes the answer. System prompt enforces the
   CITATION CONTRACT: every factual claim must reference a chunk that was
   in context (matched or hydrated) as [cite:chunk_id]; numbers/rates/
   thresholds must come from approved `facts` rows when one matches, cited
   as [fact:key]; if top retrieval score is below a settings threshold OR
   the model cannot support the answer from supplied context, it must
   output the abstention message. Post-process: strip any sentence whose
   [cite:] id was not in context.
8. `app/rag/verify.py` — for each (claim, cited chunk) pair, one
   cheap-model call: "Does this passage support this claim? yes/no".
   Unverified claims removed; if >50% of claims fail, replace the whole
   answer with the abstention message. Results recorded.
9. `app/rag/audit.py` — writes the audit_log row (matched and hydrated
   recorded separately); expose `GET /api/answers/{id}/audit`
   (auth-protected) returning question, answer, citations rendered with
   title + section_id + web_url + public_updated_at, verification results,
   and the matched/hydrated context lists.
10. Chat integration — a message in a conversation flagged `mode: 'vat'`
    (or a dedicated router, whichever fits the existing chat service better
    — decide in Phase 0) runs retrieve → answer → verify → audit, and the
    chat reply includes the citation list as structured data (pydantic
    model) for the future frontend.
11. `eval/golden.json` + `eval/run.py` — 30 golden VAT questions (write
    them: registration threshold/timing, voluntary registration, flat rate
    scheme eligibility & percentages, input tax on vehicles/entertainment/
    home office, MTD for VAT, deregistration, TOGC basics — include several
    phrased as scenarios so example-chunk retrieval is exercised — plus 5
    questions that SHOULD trigger abstention e.g. US sales tax, corporation
    tax rate, import VAT). Script reports: retrieval hit rate (expected
    base_path in top 8), citation validity, abstention correctness.

## Milestones — each gated by a test the user runs

- M0 Phase 0 audit → deliverable: docs/ARCHITECTURE_NOTES.md including the
  inventory of previously built code. STOP for review.
- M1 Migration + local Postgres w/ pgvector (docker-compose for local dev
  only) + ingest.py wired to DB → test: ingest
  /hmrc-internal-manuals/vat-registration-manual/vatreg29550 plus one
  multi-part guide; user inspects chunks via `--inspect`. Example block
  must be chunk_type 'example' AND have an embedding; guide parts must
  become separate chunks with part metadata.
- M2 Catalog + bulk VAT-registration ingest (~the VATREG manual + reg
  guides) → test: row counts, spot-check 5 chunks, re-run ingest is
  idempotent (0 new versions when nothing changed).
- M3 Hybrid retrieval + hydration → test:
  `python eval/run.py --retrieval-only` ≥ 80% hit rate on in-scope
  questions; for one scenario question, show that an 'example' chunk
  matched and its text siblings were hydrated.
- M4 Answer + verify + audit + chat integration → test: ask via the
  existing chat API with auth token; response contains verified citations
  with working gov.uk deep links; audit endpoint shows matched and
  hydrated separately; out-of-scope question abstains.
- M5 Full domestic-VAT catalog ingest + scheduled worker + eval pass →
  test: full `python eval/run.py` report committed to docs/. THE SYSTEM IS
  NOW FEATURE-COMPLETE AND TESTABLE LOCALLY. STOP for user testing.
- M6 (only after user approves M5) Cloud deployment packaging: production
  Dockerfiles for api and ingest-worker, docker-compose for the pair
  against a managed Postgres URL, health/readiness endpoints, structured
  JSON logging, env-var documentation in docs/DEPLOY.md. Target: deployable
  to any container host (Railway/Render/Fly/Cloud Run) with a managed
  Postgres (Supabase/Neon/RDS). No Kubernetes, no IaC, no CI pipeline in v1.

## Anti-complexity rules (enforced)

- No LangChain/LlamaIndex/Haystack. No message queues, no Redis, no
  Kubernetes, no GraphQL, no service mesh. Plain FastAPI + SQL + httpx.
- Cloud-READY is achieved through the two-process split, 12-factor config,
  and clean package boundaries — not by splitting into more services. Do
  not create separate repos, HTTP calls between rag/ and chat, or
  inter-service auth in v1.
- No separate components table; sibling hydration uses the chunks table.
- No abstraction until the second concrete use exists (the single-class
  VectorStore interface is the one sanctioned exception).
- Each new module ≤ ~250 lines; if it grows past that, split by
  responsibility, not by speculation.
- No feature not listed in this brief. If tempted, add a line to
  docs/LATER.md instead.
- Settings via the repo's existing mechanism (pydantic-settings if
  present); no new config framework.
- Tests: a thin integration test per milestone gate is enough; do not
  build a giant unit-test suite for v1.

## Definition of done for v1 (end of M5)

A user authenticates, asks "Do I need to register for VAT? My turnover hit
£92,000 this year" in the chat API, and receives: a correct answer citing
the approved threshold fact and the relevant registration guidance chunks,
each citation showing section/title + last-updated date + clickable gov.uk
link, all claims verifier-passed, the exchange retrievable from the audit
endpoint with matched and hydrated context listed separately — and "What's
the corporation tax rate?" politely abstains and points out it covers VAT
only. Eval report shows ≥80% retrieval hit rate and 100% citation validity
on the golden set. Only then does M6 packaging begin.

## Appendix — why pgvector over Pinecone (decision record)

1. The corpus is small: full domestic VAT is on the order of 10^4–10^5
   chunks. pgvector with an HNSW index serves this in single-digit
   milliseconds; a dedicated vector DB solves scale problems this project
   does not have.
2. Auditability requires JOINs: every retrieval must connect vectors to
   document versions, supersession state, sibling chunks (hydration),
   facts, and the audit log in one transaction. With Pinecone that becomes
   two systems to keep consistent — the exact class of accidental
   complexity this project must avoid. Sibling hydration in particular is
   one SQL query here and a cross-system merge there.
3. Hybrid search lives in one engine: tsvector full-text + vector
   similarity + metadata filters (domain, superseded_at IS NULL) compose
   in one SQL query instead of cross-system result merging.
4. Ops & cost: one managed Postgres (Supabase/Neon/RDS) instead of an
   extra vendor, network hop, API key, and bill — and pgvector is natively
   supported by all major managed-Postgres providers, so M6 deployment
   stays one database.
5. Reversibility: the VectorStore interface means moving to Pinecone
   later, if scale ever demands it, is an implementation swap — not a
   redesign.
