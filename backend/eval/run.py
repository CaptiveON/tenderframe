"""Golden-set evaluation (BRIEF component 11).

Usage (from backend/):
    python eval/run.py --retrieval-only   # fast, no LLM (M3 gate)
    python eval/run.py                     # full: + citation validity + abstention (M5 gate)
    python eval/run.py --report eval/REPORT.md   # also write a markdown report

Metrics:
  - retrieval hit rate: expected base_path/prefix appears in the top-K matched chunks
  - citation validity: every citation an answer returns is verified AND resolves to a
    chunk that is in the live corpus (or an approved fact)
  - abstention correctness: out-of-scope questions abstain; in-scope questions answer
Questions whose expected documents are not ingested are reported as not_in_corpus
and excluded from the hit rate.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.rag import Chunk, Document  # noqa: E402
from app.rag.retrieve import retrieve  # noqa: E402
from app.services.rag_service import rag_service  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden.json")


def expected_in_corpus(db, q: dict) -> bool:
    paths = q.get("expected_base_paths", [])
    prefixes = q.get("expected_prefixes", [])
    base = db.query(Document).filter(Document.superseded_at.is_(None))
    if paths and base.filter(Document.base_path.in_(paths)).count():
        return True
    return any(
        base.filter(Document.base_path.like(p + "%")).count() for p in prefixes
    )


def is_hit(q: dict, matched_base_paths: list[str]) -> bool:
    paths = set(q.get("expected_base_paths", []))
    prefixes = q.get("expected_prefixes", [])
    return any(
        bp in paths or any(bp.startswith(p) for p in prefixes)
        for bp in matched_base_paths
    )


def citation_resolves(db, chunk_id: str) -> bool:
    if chunk_id.startswith("fact:"):
        return True
    return (
        db.query(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Chunk.chunk_id == chunk_id, Document.superseded_at.is_(None))
        .count() > 0
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true",
                        help="evaluate retrieval hit rate only (no LLM)")
    parser.add_argument("--report", metavar="PATH", help="write a markdown report")
    args = parser.parse_args()

    with open(GOLDEN, encoding="utf-8") as f:
        golden = json.load(f)
    domain = golden["domain"]

    db = SessionLocal()
    hits, misses, skipped = [], [], []
    abstain_results = []     # (q, abstained_bool)
    answer_results = []      # (q, answered_bool, citations[list])
    cite_total = cite_valid = 0
    t0 = time.time()
    try:
        for q in golden["questions"]:
            ctx = retrieve(db, q["question"], domain)
            top_paths = [m.base_path for m in ctx.matched]

            if q.get("expect_abstain"):
                if args.retrieval_only:
                    abstain_results.append((q, ctx.best_similarity < settings.ABSTAIN_SCORE_THRESHOLD))
                else:
                    res = rag_service.answer_question(db, "eval", f"eval-{q['id']}", q["question"], domain)
                    abstain_results.append((q, res.abstained))
                continue

            if not expected_in_corpus(db, q):
                skipped.append(q)
                continue
            (hits if is_hit(q, top_paths) else misses).append((q, top_paths))

            if not args.retrieval_only:
                res = rag_service.answer_question(db, "eval", f"eval-{q['id']}", q["question"], domain)
                answer_results.append((q, not res.abstained, res.citations))
                for c in res.citations:
                    cite_total += 1
                    if c.verified and citation_resolves(db, c.chunk_id):
                        cite_valid += 1
    finally:
        db.close()

    evaluable = len(hits) + len(misses)
    rate = 100.0 * len(hits) / evaluable if evaluable else 0.0
    abstain_correct = sum(1 for _, ok in abstain_results if ok)
    cite_validity = 100.0 * cite_valid / cite_total if cite_total else 100.0
    answered = sum(1 for _, a, _ in answer_results if a)

    lines = []
    lines.append(f"# Eval report ({'retrieval-only' if args.retrieval_only else 'full'})")
    lines.append(f"_generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}, "
                 f"{time.time()-t0:.0f}s, gen={settings.OPENAI_GENERATION_MODEL}_\n")
    lines.append("## Retrieval")
    lines.append(f"- in-scope evaluable: **{evaluable}**, hits: **{len(hits)}**, misses: {len(misses)}")
    lines.append(f"- **HIT RATE: {rate:.0f}%** (gate ≥ 80%)")
    lines.append(f"- not_in_corpus (excluded): {[q['id'] for q in skipped]}\n")
    if not args.retrieval_only:
        lines.append("## Answering")
        lines.append(f"- in-scope answered (not abstained): **{answered}/{len(answer_results)}**")
        lines.append(f"- **CITATION VALIDITY: {cite_validity:.0f}%** ({cite_valid}/{cite_total} verified & resolve, gate = 100%)\n")
    lines.append("## Abstention")
    lines.append(f"- **{abstain_correct}/{len(abstain_results)} out-of-scope questions correctly abstained**")
    for q, ok in abstain_results:
        lines.append(f"  - Q{q['id']} {'✅' if ok else '❌ ANSWERED'}: {q['question'][:60]}")
    if misses:
        lines.append("\n## Retrieval misses")
        for q, paths in misses:
            lines.append(f"- Q{q['id']}: {q['question'][:70]}  → got {paths[:3]}")

    report = "\n".join(lines)
    print("\n" + report)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"\n[report written to {args.report}]")

    ok = rate >= 80.0 and abstain_correct == len(abstain_results)
    if not args.retrieval_only:
        ok = ok and cite_validity == 100.0
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
