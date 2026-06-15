"""Builds/refreshes the per-domain catalog of base_paths to ingest.

Two discovery routes (BRIEF component 1):
- recursive walk of child_section_groups from hmrc_manual roots,
- GOV.UK Search API filtered by HMRC organisation + ingestable document types.

Writes rows to `catalog`; never disables rows it didn't find this run (manual
curation via the `enabled` flag is preserved).
"""
import logging
import time

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.ingest.seeds import SEEDS
from app.models.rag import CatalogEntry

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.gov.uk/api/search.json"
CONTENT_URL = "https://www.gov.uk/api/content"
# document types we can adapt (must stay in sync with ingest.ADAPTERS)
INGESTABLE_DOC_TYPES = {"guide", "answer", "detailed_guide"}
SEARCH_PAGE_SIZE = 100


def _get(url: str, params: dict | None = None) -> dict:
    r = httpx.get(url, params=params, headers={"Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()


def _polite_pause() -> None:
    time.sleep(settings.GOVUK_FETCH_DELAY_MS / 1000)


def walk_manual(root_base_path: str) -> list[str]:
    """Recursively collect every section base_path under an hmrc_manual root."""
    found: list[str] = []
    visited: set[str] = set()

    def child_sections(item: dict) -> list[str]:
        paths = []
        for group in item.get("details", {}).get("child_section_groups", []):
            if (group.get("title") or "").strip().lower() == "updates":
                continue  # change-log pages, not guidance
            paths += [s["base_path"] for s in group.get("child_sections", []) if s.get("base_path")]
        return paths

    def walk(base_path: str, is_root: bool) -> None:
        if base_path in visited:
            return
        visited.add(base_path)
        item = _get(f"{CONTENT_URL}{base_path}")
        _polite_pause()
        if not is_root:
            found.append(base_path)
        for child in child_sections(item):
            walk(child, is_root=False)

    walk(root_base_path, is_root=True)
    logger.info("manual walk %s: %d sections", root_base_path, len(found))
    return found


def search_documents(query: str) -> list[tuple[str, str]]:
    """Search API → [(base_path, document_type)] for ingestable HMRC docs."""
    results: list[tuple[str, str]] = []
    start = 0
    while True:
        data = _get(SEARCH_URL, params={
            "q": query,
            "filter_organisations": "hm-revenue-customs",
            "fields": "link,content_store_document_type",
            "count": SEARCH_PAGE_SIZE,
            "start": start,
        })
        _polite_pause()
        page = data.get("results", [])
        for r in page:
            link, doc_type = r.get("link", ""), r.get("content_store_document_type")
            if doc_type in INGESTABLE_DOC_TYPES and link.startswith("/"):
                results.append((link, doc_type))
        start += len(page)
        if not page or start >= data.get("total", 0):
            break
    logger.info("search %r: %d ingestable results", query, len(results))
    return results


def refresh_catalog(db: Session, domain: str) -> dict:
    """Discover base_paths for a seeded domain and upsert catalog rows."""
    seeds = SEEDS[domain]
    discovered: dict[str, str] = {}  # base_path -> source_kind

    for base_path in seeds.get("pinned", []):
        item = _get(f"{CONTENT_URL}{base_path}")
        _polite_pause()
        discovered[base_path] = item["schema_name"]

    for root in seeds.get("manual_roots", []):
        for section in walk_manual(root):
            discovered[section] = "manual_section"

    for query in seeds.get("search_queries", []):
        for base_path, doc_type in search_documents(query):
            discovered.setdefault(base_path, doc_type)

    added = re_enabled = 0
    for base_path, source_kind in discovered.items():
        row = db.get(CatalogEntry, base_path)
        if row is None:
            db.add(CatalogEntry(base_path=base_path, domain=domain, source_kind=source_kind))
            added += 1
        elif not row.enabled:
            # explicitly seeded again → authoritative; re-enable if previously
            # disabled (e.g. an old search-sourced row that's now a pin)
            row.enabled = True
            re_enabled += 1
    db.commit()
    stats = {"domain": domain, "discovered": len(discovered),
             "added": added, "re_enabled": re_enabled}
    logger.info("catalog refresh: %s", stats)
    return stats
