"""Pydantic models at the rag/ package seams (BRIEF: boundaries between
ingest/, rag/ and chat are interfaces with pydantic models at the seams)."""
from typing import Optional

from pydantic import BaseModel


class MatchedChunk(BaseModel):
    """A chunk retrieval scored (the retrieval unit)."""
    chunk_pk: int
    chunk_id: str
    document_id: int
    version_hash: str
    score: float
    chunk_type: str
    heading_path: list[str]
    text: str
    title: str
    base_path: str
    section_id: Optional[str]
    web_url: str
    public_updated_at: Optional[str]

    model_config = {"from_attributes": True}


class HydratedChunk(BaseModel):
    """A sibling chunk added to context by hydration (not retrieval-scored)."""
    chunk_pk: int
    chunk_id: str
    document_id: int
    version_hash: str
    chunk_type: str
    heading_path: list[str]
    text: str


class Citation(BaseModel):
    """One claim → source binding, enriched for the frontend/audit rendering."""
    claim: str
    chunk_id: str                      # '[cite:...]' target, or 'fact:<key>'
    verified: bool
    title: Optional[str] = None
    section_id: Optional[str] = None
    web_url: Optional[str] = None
    public_updated_at: Optional[str] = None


class AnswerResult(BaseModel):
    """What the chat layer gets back from the RAG pipeline."""
    answer: str
    citations: list[Citation]
    abstained: bool
    audit_id: int
    model: str


class RetrievedContext(BaseModel):
    """Everything the LLM will see, plus the audit split (matched vs hydrated)."""
    question: str
    domain: str
    matched: list[MatchedChunk]
    hydrated: list[HydratedChunk]
    assembled_context: str
    top_score: float
    # Abstention signal. RRF top_score is rank-based and nearly constant, so
    # weak retrieval is detected on raw cosine similarity instead.
    best_similarity: float
