"""Batch-embed new chunks (every chunk_type) and fill chunks.embedding.

The retrieval unit is the chunk: examples and tables are embedded exactly like
text (BRIEF: excluding them from the index is forbidden).
"""
import logging

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.rag import Chunk

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


def embed_pending(db: Session) -> int:
    """Embed all chunks with no embedding yet. Returns how many were embedded."""
    if not settings.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is empty in backend/.env — embeddings cannot run. "
            "Fill it in and re-run (chunks are stored; only embeddings are pending)."
        )
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    model = settings.OPENAI_EMBEDDING_MODEL

    total = 0
    while True:
        batch = (
            db.query(Chunk)
            .filter(Chunk.embedding.is_(None))
            .order_by(Chunk.id)
            .limit(BATCH_SIZE)
            .all()
        )
        if not batch:
            break
        resp = client.embeddings.create(
            model=model,
            input=[c.text for c in batch],
            dimensions=settings.EMBEDDING_DIM,
        )
        for chunk, item in zip(batch, resp.data):
            chunk.embedding = item.embedding
        db.commit()
        total += len(batch)
        logger.info("embedded %d chunks (total %d) with %s", len(batch), total, model)
    return total
