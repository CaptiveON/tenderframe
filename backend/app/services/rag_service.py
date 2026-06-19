"""Orchestrates the RAG answer pipeline: retrieve → answer → verify → audit.

Domain-generic: the domain label arrives from the chat layer; nothing here is
domain-specific.
"""
import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.rag.answer import (
    ABSTAIN_SENTINEL,
    ABSTENTION_MESSAGE,
    DISCLAIMER,
    compose_answer,
    enforce_contract,
    strip_markers,
)
from app.rag.audit import write_audit
from app.rag.retrieve import retrieve
from app.rag.route import in_domain
from app.rag.schemas import AnswerResult, Citation, RetrievedContext
from app.rag.verify import verify_claims

logger = logging.getLogger(__name__)


class RagService:

    def answer_question(
        self, db: Session, user_id: str, conversation_id: str, question: str, domain: str
    ) -> AnswerResult:
        ctx = retrieve(db, question, domain)

        # Layer 1a: nothing relevant retrieved at all → abstain (cheap floor)
        if ctx.best_similarity < settings.ABSTAIN_SCORE_THRESHOLD:
            return self._abstain(db, user_id, conversation_id, ctx, "weak_retrieval")

        # Layer 1b: scope router — cosine can't separate scope, the small model can
        if not in_domain(question, domain):
            return self._abstain(db, user_id, conversation_id, ctx, "out_of_scope")

        raw_answer, facts = compose_answer(db, ctx)

        # Layer 2: the model itself cannot support an answer from context
        if ABSTAIN_SENTINEL in raw_answer[:40]:
            return self._abstain(db, user_id, conversation_id, ctx, "model_abstained")

        kept_sentences, claims = enforce_contract(raw_answer, ctx, facts)

        chunk_texts = {c.chunk_id: c.text for c in ctx.matched}
        chunk_texts.update({c.chunk_id: c.text for c in ctx.hydrated})
        verification = verify_claims(question, claims, chunk_texts, {f.key for f in facts})

        # Layer 3: keep only verified claims (a claim is grounded if ANY of its
        # cited passages supports it). Unverified claims are dropped, not served;
        # we abstain only if nothing verifiable survives — so everything the user
        # sees is verifier-passed, without nuking a partly-derived good answer.
        verdict_by_claim: dict[str, bool] = {}
        for v in verification:
            verdict_by_claim[v["claim"]] = verdict_by_claim.get(v["claim"], False) or v["verified"]
        failed = {c for c, ok in verdict_by_claim.items() if not ok}
        final_sentences = [s for s in kept_sentences if s not in failed]
        final_answer = " ".join(strip_markers(s) for s in final_sentences).strip()
        if not final_answer:
            return self._abstain(db, user_id, conversation_id, ctx,
                                 "all_claims_stripped", verification)
        final_answer = f"{final_answer}\n\n{DISCLAIMER}"

        citation_meta = {c.chunk_id: c for c in ctx.matched}
        citations = []
        for v in verification:
            if not v["verified"] or any(v["claim"] == s for s in failed):
                continue
            m = citation_meta.get(v["chunk_id"])
            citations.append(Citation(
                claim=strip_markers(v["claim"]),
                chunk_id=v["chunk_id"],
                verified=True,
                title=m.title if m else None,
                section_id=m.section_id if m else None,
                web_url=m.web_url if m else None,
                public_updated_at=m.public_updated_at if m else None,
            ))

        row = write_audit(db, user_id, conversation_id, ctx, final_answer,
                          citations, verification, abstained=False,
                          model=settings.OPENAI_GENERATION_MODEL)
        return AnswerResult(answer=final_answer, citations=citations,
                            abstained=False, audit_id=row.id,
                            model=settings.OPENAI_GENERATION_MODEL)

    def _abstain(
        self, db: Session, user_id: str, conversation_id: str,
        ctx: RetrievedContext, reason: str, verification: list[dict] | None = None,
    ) -> AnswerResult:
        logger.info("abstaining (%s) for question: %.60s", reason, ctx.question)
        answer = f"{ABSTENTION_MESSAGE}\n\n{DISCLAIMER}"
        row = write_audit(db, user_id, conversation_id, ctx, answer,
                          citations=[], verification=verification or
                          [{"reason": reason, "best_similarity": ctx.best_similarity}],
                          abstained=True, model=settings.OPENAI_GENERATION_MODEL)
        return AnswerResult(answer=answer, citations=[], abstained=True,
                            audit_id=row.id, model=settings.OPENAI_GENERATION_MODEL)


rag_service = RagService()
