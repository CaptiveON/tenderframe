"""Domain relevance router (BRIEF: cheap/small model for routing).

Cosine similarity ranks chunks well but cannot cleanly separate in-scope from
out-of-scope questions (their score distributions overlap), so a small-model
check reads the question and decides whether it belongs to the domain at all.
Domain-as-config: the scope description lives in the domain seed, not here.
"""
import logging

from openai import OpenAI

from app.core.config import settings
from app.ingest.seeds import SEEDS

logger = logging.getLogger(__name__)

ROUTER_PROMPT = (
    "You gate a question for an assistant that answers ONLY from this guidance "
    "domain:\n{description}\n\n"
    "IN = the question is about this domain and could be answered from its "
    "guidance. OUT = a different topic, tax, or country.\n\n"
    "QUESTION: {question}\n\n"
    "Reply with one word: in or out."
)


def in_domain(question: str, domain: str) -> bool:
    """True if the question is in scope for the domain (or no description set)."""
    desc = (SEEDS.get(domain) or {}).get("description")
    if not desc:
        return True  # nothing configured to gate on
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=settings.OPENAI_CLASSIFICATION_MODEL,
        messages=[{"role": "user", "content": ROUTER_PROMPT.format(
            description=desc, question=question)}],
    )
    verdict = (resp.choices[0].message.content or "").strip().lower()
    is_out = verdict.startswith("out") or verdict.startswith("no")
    if is_out:
        logger.info("router: out-of-scope: %.70s", question)
    return not is_out
