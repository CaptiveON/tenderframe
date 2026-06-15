"""Answer composition under the CITATION CONTRACT (BRIEF component 7).

- Every factual claim must cite a chunk that was in context as [cite:chunk_id].
- Numbers/rates/thresholds come from approved `facts` rows when one matches,
  cited as [fact:key].
- Abstain when retrieval is weak (best cosine similarity below settings
  threshold) or when the model cannot support an answer from the context.
- Post-process: strip any sentence whose [cite:] id was not in context.

(The no-regex hard rule governs GOV.UK content extraction; parsing our own
model's [cite:] markers is post-processing, not content mining.)
"""
import logging
import re
from datetime import date

from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.rag import Fact
from app.rag.schemas import RetrievedContext

logger = logging.getLogger(__name__)

ABSTAIN_SENTINEL = "ABSTAIN"

ABSTENTION_MESSAGE = (
    "I can't answer that reliably from the official guidance indexed for this "
    "service, so I won't guess. It may be outside the scope I cover."
)

DISCLAIMER = (
    "This is navigation of official GOV.UK guidance with citations, "
    "not professional advice."
)

SYSTEM_PROMPT = """You are an assistant that helps users navigate official UK government guidance. You answer ONLY from the supplied CONTEXT.

CITATION CONTRACT (mandatory):
1. Every sentence that states a fact MUST end with one or more [cite:chunk_id] markers, where chunk_id is copied EXACTLY from a context block.
2. Numbers, rates, dates and thresholds: if an entry in APPROVED FACTS matches the question, use its value and cite it as [fact:key]. Otherwise cite the context chunk that states the number.
3. Use no knowledge beyond CONTEXT and APPROVED FACTS. Do not speculate.
4. If CONTEXT does not contain enough information to answer the question, reply with exactly: ABSTAIN
5. Be concise and practical. Plain sentences; no headers."""

_CITE = re.compile(r"\[(cite|fact):([^\]]+)\]")
# Sentence boundaries: newlines; whitespace after .!? (optionally inside
# closing quotes) unless a citation marker follows; and whitespace after a
# citation cluster before a capital — models place [cite:] AFTER the stop.
_SENTENCE_SPLIT = re.compile(
    r"\n+|(?<=[.!?])\s+(?!\[)|(?<=[.!?][”\"'])\s+(?!\[)|(?<=\])\s+(?=[A-Z“\"'])"
)
_LEADING_CITES = re.compile(r"^((?:\s*\[(?:cite|fact):[^\]]+\])+)\s*(.*)$", re.S)


def approved_facts(db: Session, domain: str) -> list[Fact]:
    today = date.today()
    return (
        db.query(Fact)
        .filter(
            Fact.key.like(f"{domain}.%"),
            Fact.approved.is_(True),
            Fact.effective_from <= today,
            (Fact.effective_to.is_(None)) | (Fact.effective_to >= today),
        )
        .all()
    )


def _facts_block(facts: list[Fact]) -> str:
    if not facts:
        return "(none)"
    return "\n".join(
        f"[fact:{f.key}] = {f.value} (effective from {f.effective_from})"
        for f in facts
    )


def compose_answer(db: Session, ctx: RetrievedContext) -> tuple[str, list[Fact]]:
    """Call the strong model. Returns (raw_answer_or_ABSTAIN, facts_supplied)."""
    facts = approved_facts(db, ctx.domain)
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=settings.OPENAI_GENERATION_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"QUESTION:\n{ctx.question}\n\n"
                f"APPROVED FACTS:\n{_facts_block(facts)}\n\n"
                f"CONTEXT:\n{ctx.assembled_context}"
            )},
        ],
    )
    return (resp.choices[0].message.content or "").strip(), facts


def extract_claims(answer: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """[(sentence, [(kind, id), ...])] for sentences carrying citation markers."""
    # split, then re-attach citation clusters that ended up leading a segment
    # (whatever layout the model chose, a citation belongs to the text before it)
    segments: list[str] = []
    for raw in _SENTENCE_SPLIT.split(answer):
        seg = (raw or "").strip()
        if not seg:
            continue
        m = _LEADING_CITES.match(seg)
        if m and segments:
            segments[-1] += " " + m.group(1).strip()
            seg = m.group(2).strip()
            if not seg:
                continue
        segments.append(seg)

    claims = []
    for sentence in segments:
        refs = [(m.group(1), m.group(2).strip()) for m in _CITE.finditer(sentence)]
        claims.append((sentence, refs))
    return claims


def enforce_contract(
    answer: str, ctx: RetrievedContext, facts: list[Fact]
) -> tuple[list[str], list[tuple[str, list[tuple[str, str]]]]]:
    """Strip sentences citing ids that were not in context / approved facts.

    Returns (kept_sentences, kept_claims). Sentences with no citation at all
    are kept only if they contain no digits (politeness glue); claim-bearing
    text must be cited.
    """
    in_context = {c.chunk_id for c in ctx.matched} | {c.chunk_id for c in ctx.hydrated}
    fact_keys = {f.key for f in facts}

    kept_sentences: list[str] = []
    kept_claims: list[tuple[str, list[tuple[str, str]]]] = []
    for sentence, refs in extract_claims(answer):
        if refs:
            valid = all(
                (kind == "cite" and ref in in_context)
                or (kind == "fact" and ref in fact_keys)
                for kind, ref in refs
            )
            if not valid:
                logger.warning("stripped sentence with invalid citation: %.80s", sentence)
                continue
            kept_claims.append((sentence, refs))
            kept_sentences.append(sentence)
        else:
            if not any(ch.isdigit() for ch in sentence):
                kept_sentences.append(sentence)
            else:
                logger.warning("stripped uncited numeric sentence: %.80s", sentence)
    return kept_sentences, kept_claims


def strip_markers(text: str) -> str:
    """Remove [cite:]/[fact:] markers for the human-readable message body."""
    return re.sub(r"\s*\[(?:cite|fact):[^\]]+\]", "", text).strip()
