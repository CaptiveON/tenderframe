"""Ingest worker — the second deployable process (modular monolith, two processes).

Usage (from backend/):
    python -m app.ingest.worker                 # daily schedule (APScheduler)
    python -m app.ingest.worker --once          # one fetch+embed pass, then exit
    python -m app.ingest.worker --inspect <base_path>   # pretty-print stored chunks
"""
import argparse
import logging
import sys

from app.database import SessionLocal
from app.ingest.catalog import refresh_catalog
from app.ingest.embedder import embed_pending
from app.ingest.fetcher import run_fetch
from app.ingest.seeds import SEEDS
from app.models.rag import Chunk, Document

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def run_once() -> None:
    db = SessionLocal()
    try:
        for domain in SEEDS:
            refresh_catalog(db, domain)
        stats = run_fetch(db)
        embedded = embed_pending(db)
        logger.info("run complete: %s, embedded=%d", stats, embedded)
    finally:
        db.close()


def inspect(base_path: str) -> None:
    db = SessionLocal()
    try:
        doc = (
            db.query(Document)
            .filter(Document.base_path == base_path, Document.superseded_at.is_(None))
            .first()
        )
        if doc is None:
            print(f"No current document for {base_path}")
            return
        print(f"document: {doc.title}")
        print(f"  base_path={doc.base_path}  schema={doc.schema_name}  "
              f"section_id={doc.section_id}  version={doc.version_hash}")
        print(f"  public_updated_at={doc.public_updated_at}  retrieved_at={doc.retrieved_at}")
        chunks = (
            db.query(Chunk)
            .filter(Chunk.document_id == doc.id)
            .order_by(Chunk.chunk_index)
            .all()
        )
        print(f"  chunks: {len(chunks)}\n")
        for c in chunks:
            m = c.metadata_
            part = f"part[{m['part_index']}] '{m['part_title']}' (slug={m['part_slug']})"
            hp = " > ".join(c.heading_path) or "(intro)"
            emb = "embedded" if c.embedding is not None else "NO EMBEDDING"
            print(f"[{c.chunk_index:>3}] {c.chunk_type:<8} {emb:<13} {part}")
            print(f"      {hp}")
            print(f"      {c.chunk_id}  anchor={c.anchor}")
            preview = c.text[:160].replace("\n", " ")
            print(f"      {preview}{'…' if len(c.text) > 160 else ''}\n")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="TenderFrame ingest worker")
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    parser.add_argument("--inspect", metavar="BASE_PATH", help="pretty-print stored chunks")
    args = parser.parse_args()

    if args.inspect:
        inspect(args.inspect)
        return
    if args.once:
        run_once()
        return

    # scheduled mode: daily refresh
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()
    scheduler.add_job(run_once, "cron", hour=3, minute=0)
    logger.info("ingest worker scheduled daily at 03:00; Ctrl+C to stop")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)


if __name__ == "__main__":
    main()
