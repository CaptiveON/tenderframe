"""Fetch enabled catalog rows from the GOV.UK Content API into documents/chunks.

For each enabled catalog row: GET the Content API, compare the details-body hash
to the current documents.version_hash; if changed, insert a new document version,
mark the old one superseded, and re-chunk via the provided ingest.py walker.
Sequential with a politeness delay between requests; retry with exponential
backoff. Embeddings are filled separately by embedder.py.
"""
import hashlib
import json
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ingest.ingest import ADAPTERS, assemble_chunks, build_records, walk_body
from app.models.rag import CatalogEntry, Chunk, Document

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def fetch_content_item(base_path: str) -> dict:
    url = f"https://www.gov.uk/api/content{base_path}"
    for attempt in range(MAX_RETRIES):
        try:
            r = httpx.get(url, headers={"Accept": "application/json"}, timeout=30)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 2 ** attempt
            logger.warning("fetch failed (%s), retry in %ss: %s", base_path, wait, e)
            time.sleep(wait)


def details_hash(item: dict) -> str:
    """sha256 of the details body — the document-level version fingerprint."""
    details = item.get("details", {})
    return hashlib.sha256(
        json.dumps(details, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def store_document(db: Session, item: dict, domain: str) -> Document | None:
    """Insert a new document version + chunks. Returns None if unchanged (idempotent)."""
    base_path = item["base_path"]
    version_hash = details_hash(item)

    current = (
        db.query(Document)
        .filter(Document.base_path == base_path, Document.superseded_at.is_(None))
        .first()
    )
    if current and current.version_hash == version_hash:
        logger.info("unchanged: %s (%s)", base_path, version_hash)
        return None

    adapter = ADAPTERS.get(item["schema_name"])
    if adapter is None:
        logger.error("no adapter for schema %s (%s) — skipping", item["schema_name"], base_path)
        return None

    if current:
        current.superseded_at = datetime.now(timezone.utc)

    doc = Document(
        base_path=base_path,
        content_id=item.get("content_id"),
        schema_name=item["schema_name"],
        title=item["title"],
        description=item.get("description"),
        section_id=item.get("details", {}).get("section_id"),
        public_updated_at=item.get("public_updated_at"),
        version_hash=version_hash,
        raw_json=item,
    )
    db.add(doc)
    db.flush()  # get doc.id for the chunk FK

    # Document-order index across ALL parts — sibling hydration sorts on this.
    doc_order = 0
    for part_index, part in enumerate(adapter(item)):
        records = build_records(
            item, part, part_index, assemble_chunks(walk_body(part["body_html"]))
        )
        for rec in records:
            db.add(Chunk(
                document_id=doc.id,
                chunk_id=rec["chunk_id"],
                domain=domain,
                chunk_type=rec["metadata"]["chunk_type"],
                heading_path=rec["metadata"]["heading_path"],
                chunk_index=doc_order,
                anchor=rec["metadata"]["anchor"],
                text=rec["text"],
                metadata_=rec["metadata"],
            ))
            doc_order += 1

    db.commit()
    logger.info("stored: %s v=%s (%d chunks)%s",
                base_path, version_hash, doc_order,
                " superseding previous" if current else "")
    return doc


def run_fetch(db: Session, base_paths: list[str] | None = None) -> dict:
    """Fetch all enabled catalog rows (or an explicit subset). Returns counts."""
    q = db.query(CatalogEntry).filter(CatalogEntry.enabled.is_(True))
    if base_paths:
        q = q.filter(CatalogEntry.base_path.in_(base_paths))
    rows = q.order_by(CatalogEntry.base_path).all()

    stats = {"checked": 0, "updated": 0, "unchanged": 0, "failed": 0}
    for row in rows:
        stats["checked"] += 1
        try:
            item = fetch_content_item(row.base_path)
            if store_document(db, item, row.domain) is None:
                stats["unchanged"] += 1
            else:
                stats["updated"] += 1
        except Exception:
            db.rollback()
            stats["failed"] += 1
            logger.exception("ingest failed for %s", row.base_path)
        time.sleep(settings.GOVUK_FETCH_DELAY_MS / 1000)  # be polite
    logger.info("fetch run complete: %s", stats)
    return stats
