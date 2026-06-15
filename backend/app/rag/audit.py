"""Append-only audit log writer + trail renderer (BRIEF component 9).

The app only ever INSERTs into audit_log. matched and hydrated context are
recorded separately (AUDIT SPLIT); the citation contract applies to both.
"""
import logging

from sqlalchemy.orm import Session

from app.models.rag import AuditLog, Chunk, Document
from app.rag.schemas import Citation, RetrievedContext

logger = logging.getLogger(__name__)


def write_audit(
    db: Session,
    user_id: str,
    conversation_id: str,
    ctx: RetrievedContext,
    answer: str,
    citations: list[Citation],
    verification: list[dict],
    abstained: bool,
    model: str,
) -> AuditLog:
    row = AuditLog(
        user_id=user_id,
        conversation_id=conversation_id,
        question=ctx.question,
        domain=ctx.domain,
        matched=[{"chunk_id": m.chunk_id, "document_id": m.document_id,
                  "version_hash": m.version_hash, "score": m.score} for m in ctx.matched],
        hydrated=[{"chunk_id": h.chunk_id, "document_id": h.document_id,
                   "version_hash": h.version_hash} for h in ctx.hydrated],
        answer=answer,
        citations=[c.model_dump() for c in citations],
        verification=verification,
        abstained=abstained,
        model=model,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("audit_log #%d written (abstained=%s, %d citations)",
                row.id, abstained, len(citations))
    return row


def enrich_citation(db: Session, chunk_id: str, doc_id_by_chunk: dict[str, int]) -> dict:
    """Render one citation target with title/section/link/version metadata."""
    if chunk_id.startswith("fact:"):
        return {"chunk_id": chunk_id, "kind": "approved_fact"}
    doc_id = doc_id_by_chunk.get(chunk_id)
    q = db.query(Chunk, Document).join(Document, Chunk.document_id == Document.id)
    q = (q.filter(Chunk.chunk_id == chunk_id, Chunk.document_id == doc_id)
         if doc_id else
         q.filter(Chunk.chunk_id == chunk_id, Document.superseded_at.is_(None)))
    row = q.first()
    if row is None:
        return {"chunk_id": chunk_id, "kind": "unresolved"}
    chunk, doc = row
    return {
        "chunk_id": chunk_id,
        "kind": "chunk",
        "title": doc.title,
        "section_id": doc.section_id,
        "web_url": (chunk.metadata_ or {}).get("web_url"),
        "public_updated_at": str(doc.public_updated_at or "") or None,
        "version_hash": doc.version_hash,
    }


def render_audit(db: Session, row: AuditLog) -> dict:
    """The full trail for GET /api/v1/answers/{id}/audit."""
    doc_id_by_chunk = {m["chunk_id"]: m["document_id"] for m in row.matched}
    doc_id_by_chunk.update({h["chunk_id"]: h["document_id"] for h in row.hydrated})
    return {
        "id": row.id,
        "created_at": str(row.created_at),
        "user_id": row.user_id,
        "conversation_id": row.conversation_id,
        "domain": row.domain,
        "question": row.question,
        "answer": row.answer,
        "abstained": row.abstained,
        "model": row.model,
        "citations": [
            {**c, "source": enrich_citation(db, c.get("chunk_id", ""), doc_id_by_chunk)}
            for c in row.citations
        ],
        "verification": row.verification,
        "matched": row.matched,
        "hydrated": row.hydrated,
    }
