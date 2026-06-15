"""
ingest.py - GOV.UK Content API -> audit-ready chunks

Usage:
    python ingest.py /hmrc-internal-manuals/vat-registration-manual/vatreg29550
    python ingest.py --file ./vatreg29550.json        (offline / cached mode)

Live mode does ONE call: https://www.gov.uk/api/content/<base_path>
No regex over content. Metadata comes entirely from API fields;
structure comes from the govspeak-rendered DOM.

Deps: pip install httpx beautifulsoup4 lxml
"""

import hashlib
import json
import sys
from datetime import datetime, timezone

from bs4 import BeautifulSoup, Tag

MAX_CHUNK_CHARS = 1800  # ~450 tokens; merge stops at this budget


# ---------- 1. Fetch ----------
def fetch_content_item(arg: str) -> dict:
    if arg == "--file":
        with open(sys.argv[2], encoding="utf-8") as f:
            return json.load(f)
    import httpx

    url = f"https://www.gov.uk/api/content{arg}"
    r = httpx.get(url, headers={"Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------- 2. Schema adapters: return [{part_title, part_slug, body_html}] ----------
def _single_body(item: dict) -> list[dict]:
    return [{
        "part_title": item["title"],
        "part_slug": None,
        "body_html": item.get("details", {}).get("body", "") or "",
    }]


ADAPTERS = {
    "manual_section": _single_body,
    "hmrc_manual_section": _single_body,  # live HMRC manuals use this schema_name
    "answer": _single_body,
    "detailed_guide": _single_body,
    "guide": lambda item: [
        {"part_title": p["title"], "part_slug": p["slug"], "body_html": p.get("body", "") or ""}
        for p in item.get("details", {}).get("parts", [])
    ],
}


# ---------- 3. Govspeak-aware DOM walker ----------
# Block classification uses GOV.UK's own semantic markup - no regex on text.
def classify_block(el: Tag) -> str:
    classes = " ".join(el.get("class", []))
    if el.name == "table":
        return "table"
    if "example" in classes:
        return "example"
    if "call-to-action" in classes:
        return "action"
    if "info-notice" in classes or "application-notice" in classes:
        return "notice"
    return "text"


def table_to_markdown(table: Tag) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(strip=True).replace("|", "/") for c in tr.find_all(["th", "td"])]
        rows.append("| " + " | ".join(cells) + " |")
    if len(rows) > 1:
        cols = rows[0].count("|") - 1
        rows.insert(1, "|" + " --- |" * cols)
    return "\n".join(rows)


def walk_body(body_html: str) -> list[dict]:
    soup = BeautifulSoup(body_html, "lxml")
    root = soup.body or soup
    # Some schemas (detailed_guide, guidance pages) wrap the whole body in a
    # single container div (<div class="govspeak">). Unwrap container divs so
    # the walker sees the real block sequence - purely structural, no content
    # inspection.
    while True:
        kids = [k for k in root.find_all(recursive=False) if isinstance(k, Tag)]
        if len(kids) == 1 and kids[0].name == "div":
            root = kids[0]
        else:
            break
    blocks: list[dict] = []
    h2 = h3 = anchor = None
    # HMRC manuals often title examples with a heading rather than div.example -
    # a section whose heading text is exactly "Example(s)" is chunk_type example.
    heading_is_example = False

    for el in root.find_all(recursive=False):
        if not isinstance(el, Tag):
            continue
        if el.name == "h2":
            h2, h3 = el.get_text(strip=True), None
            anchor = el.get("id")
            heading_is_example = h2.lower() in ("example", "examples")
            continue
        if el.name == "h3":
            h3 = el.get_text(strip=True)
            anchor = el.get("id") or anchor
            heading_is_example = h3.lower() in ("example", "examples")
            continue
        # HMRC manual sections also label examples with a bare paragraph
        # (<p>Example</p>) - same trivial label check as for headings, applied
        # to a label-only <p>. The label itself is not content; blocks that
        # follow are the example, until the next h2/h3 resets the flag.
        if el.name == "p" and el.get_text(strip=True).lower() in ("example", "examples"):
            heading_is_example = True
            continue
        btype = classify_block(el)
        if btype == "text" and heading_is_example:
            btype = "example"
        content = table_to_markdown(el) if btype == "table" else el.get_text("\n", strip=True)
        if not content:
            continue
        blocks.append({
            "type": btype,
            "content": content,
            "heading_path": [h for h in (h2, h3) if h],
            "anchor": anchor,
        })
    return blocks


# ---------- 4. Chunk assembly: merge adjacent blocks of same section+type ----------
def assemble_chunks(blocks: list[dict]) -> list[dict]:
    chunks: list[dict] = []
    for b in blocks:
        last = chunks[-1] if chunks else None
        mergeable = (
            last
            and last["chunk_type"] == b["type"]
            and last["heading_path"] == b["heading_path"]
            and len(last["text"]) + len(b["content"]) + 2 <= MAX_CHUNK_CHARS
        )
        if mergeable:
            last["text"] += "\n\n" + b["content"]
        else:
            chunks.append({
                "chunk_type": b["type"],
                "heading_path": b["heading_path"],
                "anchor": b["anchor"],
                "text": b["content"],
            })
    return chunks


# ---------- 5. Metadata envelope: everything from API fields ----------
def build_records(item: dict, part: dict, part_index: int, chunks: list[dict]) -> list[dict]:
    details = item.get("details", {})
    version_hash = hashlib.sha256(part["body_html"].encode()).hexdigest()[:16]
    org = (item.get("links", {}).get("organisations") or [{}])[0].get("title")
    withdrawn = bool(item.get("withdrawn_notice", {}).get("withdrawn_at"))

    records = []
    for i, c in enumerate(chunks):
        frag = f"#{c['anchor']}" if c["anchor"] else ""
        records.append({
            "chunk_id": f"{item['base_path']}#{part['part_slug'] or 'body'}:{i}",
            "text": c["text"],
            "metadata": {
                # identity & citation address
                "content_id": item.get("content_id"),
                "base_path": item["base_path"],
                "web_url": f"https://www.gov.uk{item['base_path']}{frag}",
                "schema_name": item["schema_name"],
                "document_type": item.get("document_type"),
                "section_id": details.get("section_id"),          # e.g. VATREG29550
                "manual": (details.get("manual") or {}).get("base_path"),
                "breadcrumbs": [b.get("section_id") for b in details.get("breadcrumbs", [])],
                "part_title": part["part_title"],
                "part_slug": part["part_slug"],
                "part_index": part_index,
                "heading_path": c["heading_path"],                # [h2, h3]
                "anchor": c["anchor"],
                "chunk_index": i,
                "chunk_type": c["chunk_type"],                    # text|example|table|action|notice
                # versioning & audit
                "first_published_at": item.get("first_published_at"),
                "public_updated_at": item.get("public_updated_at"),
                "version_hash": version_hash,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "withdrawn": withdrawn,
                # provenance
                "organisation": org,
                "title": item["title"],
                "description": item.get("description"),
                "locale": item.get("locale"),
            },
        })
    return records


# ---------- main ----------
def main() -> None:
    item = fetch_content_item(sys.argv[1])
    adapter = ADAPTERS.get(item["schema_name"])
    if adapter is None:
        raise SystemExit(f"No adapter for schema {item['schema_name']}")

    records = []
    for idx, part in enumerate(adapter(item)):
        records += build_records(item, part, idx, assemble_chunks(walk_body(part["body_html"])))

    with open("chunks.json", "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"schema={item['schema_name']}  section={item.get('details', {}).get('section_id')}  chunks={len(records)}")
    for r in records:
        hp = " > ".join(r["metadata"]["heading_path"]) or "(intro)"
        print(f" - [{r['metadata']['chunk_type']}] {hp}  {len(r['text'])} chars")


if __name__ == "__main__":
    main()
