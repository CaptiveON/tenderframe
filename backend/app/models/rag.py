from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import declarative_base, relationship

from app.core.config import settings

# Separate Base on purpose: these five tables are owned by Alembic
# (alembic/versions/0001_rag_schema.py), NOT by the create_all() call in
# app/models/__init__.py. Keeping them off the main Base guarantees create_all
# can never emit conflicting DDL for them (generated tsv column, vector type).
RagBase = declarative_base()


class CatalogEntry(RagBase):
    __tablename__ = "catalog"

    base_path = Column(Text, primary_key=True)
    domain = Column(Text, nullable=False)
    source_kind = Column(Text, nullable=False)  # manual_section | guide | answer | detailed_guide
    enabled = Column(Boolean, nullable=False, default=True)
    added_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class Document(RagBase):
    __tablename__ = "documents"

    id = Column(BigInteger, primary_key=True)
    base_path = Column(Text, nullable=False)
    content_id = Column(Text)
    schema_name = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text)
    section_id = Column(Text)  # e.g. VATREG29550
    public_updated_at = Column(DateTime(timezone=True))
    version_hash = Column(Text, nullable=False)  # sha256 of details body
    raw_json = Column(JSONB, nullable=False)  # full ContentItem, the audit source of truth
    retrieved_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    superseded_at = Column(DateTime(timezone=True))  # null = current version

    chunks = relationship("Chunk", back_populates="document")


class Chunk(RagBase):
    __tablename__ = "chunks"

    id = Column(BigInteger, primary_key=True)
    document_id = Column(BigInteger, ForeignKey("documents.id"), nullable=False)
    chunk_id = Column(Text, nullable=False)  # '/path#part:idx' as in ingest.py
    domain = Column(Text, nullable=False)
    chunk_type = Column(Text, nullable=False)  # text | example | table | action | notice
    heading_path = Column(ARRAY(Text), nullable=False, default=list)
    chunk_index = Column(Integer, nullable=False)  # document order, for sibling hydration
    anchor = Column(Text)
    text = Column(Text, nullable=False)
    # tsv is a GENERATED column — intentionally unmapped so the ORM never writes it
    embedding = Column(Vector(settings.EMBEDDING_DIM))  # populated for EVERY chunk_type
    metadata_ = Column("metadata", JSONB, nullable=False)  # full envelope from ingest.py

    document = relationship("Document", back_populates="chunks")


class Fact(RagBase):
    __tablename__ = "facts"

    key = Column(Text, primary_key=True)  # 'vat.registration_threshold'
    effective_from = Column(Date, primary_key=True)
    value = Column(Text, nullable=False)
    effective_to = Column(Date)
    source_chunk_id = Column(Text, nullable=False)
    approved = Column(Boolean, nullable=False, default=False)


class AuditLog(RagBase):
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(Text, nullable=False)
    conversation_id = Column(Text, nullable=False)
    question = Column(Text, nullable=False)
    domain = Column(Text)
    matched = Column(JSONB, nullable=False)  # [{chunk_id, document_id, version_hash, score}]
    hydrated = Column(JSONB, nullable=False)  # [{chunk_id, document_id, version_hash}]
    answer = Column(Text, nullable=False)
    citations = Column(JSONB, nullable=False)  # [{claim, chunk_id, verified}]
    verification = Column(JSONB, nullable=False)  # per-claim entailment results
    abstained = Column(Boolean, nullable=False, default=False)
    model = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
