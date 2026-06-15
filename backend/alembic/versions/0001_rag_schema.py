"""RAG schema: catalog, documents, chunks, facts, audit_log (BRIEF data model)

Revision ID: 0001
Revises:
Create Date: 2026-06-10
"""
from alembic import op

from app.core.config import settings

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Frozen into the column at creation time (ARCHITECTURE_NOTES R4).
EMBEDDING_DIM = settings.EMBEDDING_DIM


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # what to ingest; seeded for VAT, rows added for future domains
    op.execute("""
        CREATE TABLE catalog (
          base_path     text PRIMARY KEY,
          domain        text NOT NULL,
          source_kind   text NOT NULL,
          enabled       boolean NOT NULL DEFAULT true,
          added_at      timestamptz NOT NULL DEFAULT now()
        )
    """)

    # one row per (base_path, version); never delete, only supersede
    op.execute("""
        CREATE TABLE documents (
          id                bigserial PRIMARY KEY,
          base_path         text NOT NULL,
          content_id        text,
          schema_name       text NOT NULL,
          title             text NOT NULL,
          description       text,
          section_id        text,
          public_updated_at timestamptz,
          version_hash      text NOT NULL,
          raw_json          jsonb NOT NULL,
          retrieved_at      timestamptz NOT NULL DEFAULT now(),
          superseded_at     timestamptz,
          UNIQUE (base_path, version_hash)
        )
    """)

    op.execute(f"""
        CREATE TABLE chunks (
          id            bigserial PRIMARY KEY,
          document_id   bigint NOT NULL REFERENCES documents(id),
          chunk_id      text NOT NULL,
          domain        text NOT NULL,
          chunk_type    text NOT NULL,
          heading_path  text[] NOT NULL DEFAULT '{{}}',
          chunk_index   int  NOT NULL,
          anchor        text,
          text          text NOT NULL,
          tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
          embedding     vector({EMBEDDING_DIM}),
          metadata      jsonb NOT NULL,
          UNIQUE (chunk_id, document_id)
        )
    """)
    op.execute("CREATE INDEX chunks_tsv_idx ON chunks USING gin(tsv)")
    op.execute("CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX chunks_domain_idx ON chunks (domain)")
    op.execute("CREATE INDEX chunks_sibling_idx ON chunks (document_id, chunk_index)")

    # curated hard numbers; LLM-proposed at ingestion, human-approved before use
    op.execute("""
        CREATE TABLE facts (
          key             text NOT NULL,
          value           text NOT NULL,
          effective_from  date NOT NULL,
          effective_to    date,
          source_chunk_id text NOT NULL,
          approved        boolean NOT NULL DEFAULT false,
          PRIMARY KEY (key, effective_from)
        )
    """)

    # append-only; the app never issues UPDATE or DELETE against this table
    op.execute("""
        CREATE TABLE audit_log (
          id              bigserial PRIMARY KEY,
          user_id         text NOT NULL,
          conversation_id text NOT NULL,
          question        text NOT NULL,
          domain          text,
          matched         jsonb NOT NULL,
          hydrated        jsonb NOT NULL,
          answer          text NOT NULL,
          citations       jsonb NOT NULL,
          verification    jsonb NOT NULL,
          abstained       boolean NOT NULL DEFAULT false,
          model           text NOT NULL,
          created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("DROP TABLE IF EXISTS facts")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS catalog")
