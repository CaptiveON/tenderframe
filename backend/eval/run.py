"""Golden-set evaluation (BRIEF component 11).

Usage (from backend/):
    python eval/run.py --retrieval-only

Reports, per the brief: retrieval hit rate (expected base_path in top 8),
abstention signal, and — once M4 lands — citation validity and abstention
correctness. Questions whose expected documents are not yet ingested are
reported separately as not_in_corpus and excluded from the hit rate.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.rag import Document  # noqa: E402
from app.rag.retrieve import retrieve  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden.json")


def expected_in_corpus(db, q: dict) -> bool:
    paths = q.get("expected_base_paths", [])
    prefixes = q.get("expected_prefixes", [])
    query = db.query(Document).filter(Document.superseded_at.is_(None))
    if paths and query.filter(Document.base_path.in_(paths)).count():
        return True
    for p in prefixes:
        if (db.query(Document)
                .filter(Document.superseded_at.is_(None), Document.base_path.like(p + "%"))
                .count()):
            return True
    return False


def is_hit(q: dict, matched_base_paths: list[str]) -> bool:
    paths = set(q.get("expected_base_paths", []))
    prefixes = q.get("expected_prefixes", [])
    for bp in matched_base_paths:
        if bp in paths or any(bp.startswith(p) for p in prefixes):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval-only", action="store_true",
                        help="evaluate retrieval hit rate only (M3 gate)")
    args = parser.parse_args()
    if not args.retrieval_only:
        print("Answer/citation evaluation arrives with M4; running retrieval-only.")

    with open(GOLDEN, encoding="utf-8") as f:
        golden = json.load(f)
    domain = golden["domain"]

    db = SessionLocal()
    hits, misses, skipped, abstain_rows, sim_rows = [], [], [], [], []
    t0 = time.time()
    try:
        for q in golden["questions"]:
            ctx = retrieve(db, q["question"], domain)
            top_paths = [m.base_path for m in ctx.matched]
            if q.get("expect_abstain"):
                abstain_rows.append((q, ctx.best_similarity, top_paths[:2]))
                continue
            sim_rows.append(ctx.best_similarity)
            if not expected_in_corpus(db, q):
                skipped.append(q)
                continue
            (hits if is_hit(q, top_paths) else misses).append((q, top_paths))
    finally:
        db.close()

    evaluable = len(hits) + len(misses)
    rate = 100.0 * len(hits) / evaluable if evaluable else 0.0

    print(f"\n=== RETRIEVAL EVAL ({time.time()-t0:.0f}s) ===")
    print(f"in-scope evaluable: {evaluable}   hits: {len(hits)}   misses: {len(misses)}")
    print(f"HIT RATE: {rate:.0f}%   (gate: >= 80%)")
    print(f"not_in_corpus (excluded, pending M5): {[q['id'] for q in skipped]}")

    if misses:
        print("\n--- misses ---")
        for q, paths in misses:
            print(f"  Q{q['id']}: {q['question'][:70]}")
            for p in paths[:3]:
                print(f"      got: {p}")

    print("\n--- abstention questions (informational at M3; best cosine similarity) ---")
    print(f"    abstain similarity threshold (settings): {settings.ABSTAIN_SCORE_THRESHOLD}")
    if sim_rows:
        print(f"    in-scope similarity range: {min(sim_rows):.3f} – {max(sim_rows):.3f}")
    for q, sim, top in abstain_rows:
        flag = "would abstain" if sim < settings.ABSTAIN_SCORE_THRESHOLD else "would ANSWER (bad)"
        print(f"  Q{q['id']}: best_sim={sim:.3f} [{flag}] {q['question'][:55]}")

    sys.exit(0 if rate >= 80.0 else 1)


if __name__ == "__main__":
    main()
