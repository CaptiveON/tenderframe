"""Per-claim entailment verification (BRIEF component 8).

For each (claim, cited chunk) pair, one cheap-model call: does the passage
support the claim? Unverified claims are removed by the orchestrator; if more
than half fail, the whole answer is replaced with the abstention message.
Fact citations ([fact:key]) are human-approved and pass without a model call.
"""
import logging

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

VERIFY_PROMPT = (
    "PASSAGE:\n{passage}\n\n"
    "CLAIM:\n{claim}\n\n"
    "Does the passage support the claim? Answer strictly 'yes' or 'no'."
)


def verify_claim(passage: str, claim: str) -> bool:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=settings.OPENAI_CLASSIFICATION_MODEL,
        messages=[{"role": "user", "content": VERIFY_PROMPT.format(passage=passage, claim=claim)}],
    )
    verdict = (resp.choices[0].message.content or "").strip().lower()
    return verdict.startswith("yes")


def verify_claims(
    claims: list[tuple[str, list[tuple[str, str]]]],
    chunk_texts: dict[str, str],
    fact_keys: set[str],
) -> list[dict]:
    """Returns per-claim results:
    [{claim, chunk_id, verified, method}] — one entry per (claim, ref) pair.
    """
    results = []
    for sentence, refs in claims:
        for kind, ref in refs:
            if kind == "fact" and ref in fact_keys:
                results.append({"claim": sentence, "chunk_id": f"fact:{ref}",
                                "verified": True, "method": "approved_fact"})
                continue
            passage = chunk_texts.get(ref, "")
            ok = bool(passage) and verify_claim(passage, sentence)
            results.append({"claim": sentence, "chunk_id": ref,
                            "verified": ok, "method": settings.OPENAI_CLASSIFICATION_MODEL})
            if not ok:
                logger.warning("claim failed verification: %.80s [%s]", sentence, ref)
    return results
