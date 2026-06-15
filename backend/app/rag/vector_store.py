"""VectorStore interface + the single sanctioned implementation (PgVectorStore).

BRIEF: one class, one implementation — so a managed vector DB could be swapped
later WITHOUT building a second implementation now. Full-text search lives on
PgVectorStore too (it is inherently Postgres and pairs with the vector side in
one engine).

Both searches filter to current document versions (superseded_at IS NULL) and
the requested domain.
"""
from abc import ABC, abstractmethod

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.models.rag import Chunk, Document


class VectorStore(ABC):
    @abstractmethod
    def vector_search(
        self, db: Session, embedding: list[float], domain: str, limit: int
    ) -> list[tuple[int, float]]:
        """Return [(chunk_pk, cosine_distance)] best-first."""


class PgVectorStore(VectorStore):
    def vector_search(
        self, db: Session, embedding: list[float], domain: str, limit: int
    ) -> list[tuple[int, float]]:
        distance = Chunk.embedding.cosine_distance(embedding)
        rows = (
            db.query(Chunk.id, distance.label("distance"))
            .join(Document, Chunk.document_id == Document.id)
            .filter(
                Document.superseded_at.is_(None),
                Chunk.domain == domain,
                Chunk.embedding.isnot(None),
            )
            .order_by("distance")
            .limit(limit)
            .all()
        )
        return [(pk, float(d)) for pk, d in rows]

    def fulltext_search(
        self, db: Session, query: str, domain: str, limit: int
    ) -> list[tuple[int, float]]:
        """Postgres FTS over the generated tsv column, ranked by ts_rank."""
        rows = db.execute(
            sql_text("""
                SELECT c.id, ts_rank(c.tsv, websearch_to_tsquery('english', :q)) AS rank
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.superseded_at IS NULL
                  AND c.domain = :domain
                  AND c.tsv @@ websearch_to_tsquery('english', :q)
                ORDER BY rank DESC
                LIMIT :limit
            """),
            {"q": query, "domain": domain, "limit": limit},
        ).all()
        return [(pk, float(rank)) for pk, rank in rows]
