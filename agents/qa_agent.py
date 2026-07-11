import logging
from typing import List, Optional

from pydantic import BaseModel, Field

from agents.rule_engine import detect_query_intent
from database import crud
from services.retrieval_service import compress_context, perform_hybrid_search
from utils.llm_client import invoke_llm_structured

logger = logging.getLogger(__name__)

MAX_LQ_RAG_ITERATIONS = 3
TRUST_THRESHOLD = 70


class Citation(BaseModel):
    document_id: str
    section_name: str
    text_snippet: str


class QAResult(BaseModel):
    answer: str = Field(description="The comprehensive answer based strictly on the context provided.")
    supporting_clauses: List[str] = Field(description="List of specific clause strings that directly support the answer.")
    citation_references: List[Citation] = Field(description="List of exact citations pointing to source documents.")
    confidence_score: int = Field(description="Confidence score from 0 to 100.")
    context_used: str = Field(default="", description="The raw context string used to generate this answer.")
    iteration_count: int = Field(default=1, description="Number of LQ-RAG iterations performed.")
    refinement_history: List[str] = Field(default_factory=list, description="Refinement feedback from each audit loop iteration.")


class AuditFeedback(BaseModel):
    is_grounded: bool = Field(description="True if the answer is fully grounded in the provided context.")
    trust_score: int = Field(description="Trust score from 0 to 100.")
    feedback: str = Field(description="Specific feedback on what is wrong or unsupported.")
    unsupported_claims: List[str] = Field(description="List of claims not supported by the source context.")


def _generate_answer(query: str, context_str: str, refinement_feedback: str = "") -> QAResult:
    """Single-pass answer generation using Groq LLM."""
    system_instruction = (
        "You are an expert corporate legal counsel and LQ-RAG QA Agent. "
        "Answer the user's question using strictly the provided context blocks. "
        "Do not hallucinate or use outside knowledge. If the answer is not in the context, say so clearly. "
        "Provide a comprehensive 'answer', 'supporting_clauses' texts, 'citation_references' with document IDs and section names, "
        "and a 'confidence_score' (0-100)."
    )

    refinement_section = ""
    if refinement_feedback:
        refinement_section = (
            f"\n\nIMPORTANT - Previous Audit Feedback (you MUST address these issues):\n"
            f"{refinement_feedback}\n"
            f"Revise your answer to fix the flagged issues. Remove any unsupported claims."
        )

    prompt = (
        f"Retrieved Context:\n{context_str}\n\n"
        f"User Question:\n{query}{refinement_section}"
    )

    result = invoke_llm_structured(system_instruction, prompt, QAResult)
    result.context_used = context_str
    return result


def _audit_answer(context_str: str, answer: str) -> AuditFeedback:
    """Audit pass: verifies the generated answer is grounded in context."""
    system_instruction = (
        "You are a strict Legal AI Audit Agent. Verify whether the generated answer "
        "is 100% grounded in the provided source context. "
        "Check every claim against the context. Flag unsupported claims. "
        "Return is_grounded=True only if ALL claims are supported."
    )
    prompt = (
        f"--- SOURCE CONTEXT ---\n{context_str}\n\n"
        f"--- GENERATED ANSWER TO AUDIT ---\n{answer}"
    )

    return invoke_llm_structured(system_instruction, prompt, AuditFeedback)


def answer_legal_question(query: str, doc_id: Optional[str] = None) -> QAResult:
    """Agent 9: LQ-RAG Legal Question Answering Agent.

    Full LQ-RAG recursive feedback loop:
        Question → BGE-M3 Embedding → Vector Retrieval → BGE Reranker
        → Groq LLM Generation → Audit Verification → Prompt Refinement
        → Recursive Feedback Loop → Verified Response
    """
    intent_filter = detect_query_intent(query)
    retrieved_docs = perform_hybrid_search(query, doc_id, k=5)

    retrieved_chunk_ids = [d.metadata.get("clause_id") for d in retrieved_docs if d.metadata.get("clause_id") is not None]
    try:
        crud.log_retrieval(
            query_text=query, doc_id_scope=doc_id,
            detected_intent_filter=str(intent_filter) if intent_filter else None,
            retrieved_chunk_ids=retrieved_chunk_ids,
        )
    except Exception:
        logger.exception("Failed to log retrieval history (non-fatal)")

    if not retrieved_docs:
        return QAResult(
            answer="I could not find any relevant information in the documents to answer your question.",
            supporting_clauses=[], citation_references=[], confidence_score=0,
        )

    context_str = compress_context(query, retrieved_docs)

    refinement_feedback = ""
    refinement_history = []
    final_result = None

    for iteration in range(1, MAX_LQ_RAG_ITERATIONS + 1):
        logger.info(f"LQ-RAG iteration {iteration}/{MAX_LQ_RAG_ITERATIONS}")

        try:
            result = _generate_answer(query, context_str, refinement_feedback)
            result.iteration_count = iteration

            audit = _audit_answer(context_str, result.answer)

            if audit.is_grounded and audit.trust_score >= TRUST_THRESHOLD:
                logger.info(f"LQ-RAG converged at iteration {iteration} (trust: {audit.trust_score})")
                result.refinement_history = refinement_history
                return result

            refinement_feedback = f"Trust Score: {audit.trust_score}/100\n"
            refinement_feedback += f"Audit Feedback: {audit.feedback}\n"
            if audit.unsupported_claims:
                refinement_feedback += "Unsupported Claims to Remove:\n"
                for claim in audit.unsupported_claims:
                    refinement_feedback += f"  - {claim}\n"

            refinement_history.append(
                f"Iteration {iteration}: Trust={audit.trust_score}, Grounded={audit.is_grounded}, "
                f"Issues={audit.feedback}"
            )
            final_result = result

        except Exception as e:
            logger.error(f"LQ-RAG iteration {iteration} failed: {e}")
            if final_result:
                final_result.refinement_history = refinement_history
                return final_result
            return QAResult(
                answer=f"An error occurred while generating the answer: {e}",
                supporting_clauses=[], citation_references=[], confidence_score=0,
            )

    if final_result:
        final_result.refinement_history = refinement_history
        return final_result

    return QAResult(
        answer="Unable to generate a verified answer after multiple attempts.",
        supporting_clauses=[], citation_references=[], confidence_score=0,
    )
