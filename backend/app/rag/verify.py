"""Per-claim entailment verification (BRIEF component 8).

For each (claim, cited chunk) pair, one cheap-model call: does the passage
support the claim? Unverified claims are removed by the orchestrator; if more
than half fail, the whole answer is replaced with the abstention message.
Fact citations ([fact:key]) are human-approved and pass without a model call.

The claim is stripped of its [cite:]/[fact:] markers before the check (the
markers are not part of the assertion), and the prompt accepts a claim that
correctly *applies* a rule/figure from the passage, not only verbatim restatement.
"""
import logging

from openai import OpenAI

from app.core.config import settings
from app.rag.answer import strip_markers

logger = logging.getLogger(__name__)

VERIFY_PROMPT = (
    "You check whether a CLAIM in an answer is supported by official guidance.\n"
    "It is SUPPORTED if the PASSAGE states it, or if the claim correctly applies a "
    "rule or value from the PASSAGE to the facts supplied in the QUESTION. The rule "
    "must come from the PASSAGE; the QUESTION only supplies the user's own facts. "
    "Otherwise it is NOT supported.\n\n"
    "QUESTION:\n{question}\n\n"
    "PASSAGE:\n{passage}\n\n"
    "CLAIM:\n{claim}\n\n"
    "Reply with one word: yes or no."
)


def verify_claim(question: str, passage: str, claim: str) -> bool:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=settings.OPENAI_CLASSIFICATION_MODEL,
        messages=[{"role": "user", "content": VERIFY_PROMPT.format(
            question=question, passage=passage, claim=claim)}],
    )
    verdict = (resp.choices[0].message.content or "").strip().lower()
    return verdict.startswith("yes")


def verify_claims(
    question: str,
    claims: list[tuple[str, list[tuple[str, str]]]],
    chunk_texts: dict[str, str],
    fact_keys: set[str],
) -> list[dict]:
    """Returns per-(claim, ref) results: [{claim, chunk_id, verified, method}].
    `claim` keeps its original markers (the orchestrator matches on it); the
    verifier sees the marker-free assertion.
    """
    results = []
    for sentence, refs in claims:
        clean = strip_markers(sentence)
        for kind, ref in refs:
            if kind == "fact" and ref in fact_keys:
                results.append({"claim": sentence, "chunk_id": f"fact:{ref}",
                                "verified": True, "method": "approved_fact"})
                continue
            passage = chunk_texts.get(ref, "")
            ok = bool(passage) and verify_claim(question, passage, clean)
            results.append({"claim": sentence, "chunk_id": ref,
                            "verified": ok, "method": settings.OPENAI_CLASSIFICATION_MODEL})
            if not ok:
                logger.warning("claim failed verification: %.80s [%s]", clean, ref)
    return results
