"""Hybrid retrieval + sibling hydration (BRIEF core design).

RETRIEVAL UNIT = the chunk: pgvector cosine + Postgres FTS, top
RETRIEVAL_PER_SIDE each, merged with Reciprocal Rank Fusion to
RETRIEVAL_TOP_K matched chunks.

ANSWER UNIT = the section: for each matched chunk, hydrate siblings (same
document, same top-level heading) in document order, within the hydration
budget. Trim priority: matched chunks, then sibling examples, then sibling
tables, then remaining sibling text.
"""
import logging
from collections import defaultdict

from openai import OpenAI
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.rag import Chunk, Document
from app.rag.schemas import HydratedChunk, MatchedChunk, RetrievedContext
from app.rag.vector_store import PgVectorStore

logger = logging.getLogger(__name__)

RRF_K = 60
CHARS_PER_TOKEN = 4  # budget estimate
_TRIM_PRIORITY = {"example": 0, "table": 1, "action": 2, "notice": 2, "text": 3}

_store = PgVectorStore()


def embed_query(question: str) -> list[float]:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=[question],
        dimensions=settings.EMBEDDING_DIM,
    ).data[0].embedding


def rrf_merge(rankings: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, pk in enumerate(ranking):
            scores[pk] += 1.0 / (k + rank + 1)
    return dict(scores)


def _top_heading(heading_path: list[str]) -> str:
    return heading_path[0] if heading_path else ""


def _siblings(db: Session, document_id: int, top_heading: str) -> list[Chunk]:
    """All chunks of the section: same document, same top-level heading."""
    return (
        db.query(Chunk)
        .filter(
            Chunk.document_id == document_id,
            func.coalesce(Chunk.heading_path[1], "") == top_heading,
        )
        .order_by(Chunk.chunk_index)
        .all()
    )


def _hydrate(db: Session, matched_chunks: list[Chunk], scores: dict[int, float]):
    """Group matched chunks into sections, hydrate siblings within budget.

    Returns (ordered_section_chunks, hydrated_pks): sections best-first, each a
    list of Chunk in document order; hydrated_pks = included non-matched pks.
    """
    matched_pks = {c.id for c in matched_chunks}
    budget_chars = settings.HYDRATION_MAX_TOKENS * CHARS_PER_TOKEN

    # sections keyed by (document_id, top_heading), ranked by their best chunk
    section_best: dict[tuple, float] = {}
    for c in matched_chunks:
        key = (c.document_id, _top_heading(c.heading_path))
        section_best[key] = max(section_best.get(key, 0.0), scores.get(c.id, 0.0))
    sections = sorted(section_best, key=section_best.get, reverse=True)
    sections = sections[: settings.HYDRATION_MAX_SECTIONS]

    ordered_sections: list[list[Chunk]] = []
    hydrated_pks: list[int] = []
    for doc_id, top in sections:
        sibs = _siblings(db, doc_id, top)
        # selection order: matched first, then examples, tables, rest
        def sel_key(c: Chunk) -> tuple:
            return (0 if c.id in matched_pks else 1 + _TRIM_PRIORITY.get(c.chunk_type, 3),
                    c.chunk_index)
        used = 0
        chosen: list[Chunk] = []
        for c in sorted(sibs, key=sel_key):
            cost = len(c.text)
            if c.id not in matched_pks and used + cost > budget_chars:
                continue
            chosen.append(c)
            used += cost
        chosen.sort(key=lambda c: c.chunk_index)  # feed the LLM in document order
        ordered_sections.append(chosen)
        hydrated_pks += [c.id for c in chosen if c.id not in matched_pks]
    return ordered_sections, hydrated_pks


def _assemble(db: Session, ordered_sections: list[list[Chunk]]) -> str:
    """Render sections for the LLM; every chunk is addressable for [cite:]."""
    doc_ids = {c.document_id for sec in ordered_sections for c in sec}
    docs = {d.id: d for d in db.query(Document).filter(Document.id.in_(doc_ids))}
    parts = []
    for sec in ordered_sections:
        if not sec:
            continue
        d = docs[sec[0].document_id]
        head = _top_heading(sec[0].heading_path)
        label = f"{d.title}" + (f" — {head}" if head else "")
        ref = d.section_id or d.base_path
        parts.append(f"### {label} ({ref})")
        for c in sec:
            parts.append(f"[cite:{c.chunk_id}] ({c.chunk_type})\n{c.text}")
    return "\n\n".join(parts)


def retrieve(db: Session, question: str, domain: str) -> RetrievedContext:
    emb = embed_query(question)
    vec = _store.vector_search(db, emb, domain, settings.RETRIEVAL_PER_SIDE)
    fts = _store.fulltext_search(db, question, domain, settings.RETRIEVAL_PER_SIDE)
    scores = rrf_merge([[pk for pk, _ in vec], [pk for pk, _ in fts]])

    top_pks = sorted(scores, key=scores.get, reverse=True)[: settings.RETRIEVAL_TOP_K]
    chunk_map = {c.id: c for c in db.query(Chunk).filter(Chunk.id.in_(top_pks))}
    matched_chunks = [chunk_map[pk] for pk in top_pks if pk in chunk_map]

    doc_ids = {c.document_id for c in matched_chunks}
    docs = {d.id: d for d in db.query(Document).filter(Document.id.in_(doc_ids))}

    matched = [
        MatchedChunk(
            chunk_pk=c.id, chunk_id=c.chunk_id, document_id=c.document_id,
            version_hash=docs[c.document_id].version_hash,
            score=scores[c.id], chunk_type=c.chunk_type,
            heading_path=c.heading_path, text=c.text,
            title=docs[c.document_id].title,
            base_path=docs[c.document_id].base_path,
            section_id=docs[c.document_id].section_id,
            web_url=(c.metadata_ or {}).get("web_url", ""),
            public_updated_at=str(docs[c.document_id].public_updated_at or "") or None,
        )
        for c in matched_chunks
    ]

    ordered_sections, hydrated_pks = _hydrate(db, matched_chunks, scores)
    hyd_map = {c.id: c for sec in ordered_sections for c in sec if c.id in set(hydrated_pks)}
    hyd_docs = {d.id: d for d in db.query(Document).filter(
        Document.id.in_({c.document_id for c in hyd_map.values()} or {0}))}
    hydrated = [
        HydratedChunk(
            chunk_pk=c.id, chunk_id=c.chunk_id, document_id=c.document_id,
            version_hash=hyd_docs[c.document_id].version_hash,
            chunk_type=c.chunk_type, heading_path=c.heading_path, text=c.text,
        )
        for c in hyd_map.values()
    ]

    ctx = RetrievedContext(
        question=question, domain=domain, matched=matched, hydrated=hydrated,
        assembled_context=_assemble(db, ordered_sections),
        top_score=max(scores.values(), default=0.0),
        best_similarity=(1.0 - vec[0][1]) if vec else 0.0,
    )
    logger.info("retrieve: %d matched, %d hydrated, top_score=%.4f",
                len(matched), len(hydrated), ctx.top_score)
    return ctx
