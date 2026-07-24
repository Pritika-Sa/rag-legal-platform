import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agents.hallucination_agent import evaluate_hallucination
from database import crud
from services.retrieval_service import build_prompt_context, perform_vector_search
from utils.llm_client import invoke_llm_structured

logger = logging.getLogger(__name__)


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
    # Typed `Any`, not `Optional[Dict[str, Any]]`, on purpose: this is the
    # schema invoke_llm_structured() uses for the LLM answer-generation call
    # itself, which asks the model to fill in every declared field and
    # validates whatever it returns. `Any` always validates regardless of
    # the placeholder the LLM emits here; the real dict is written in by
    # answer_legal_question() afterwards, exactly like the pre-existing
    # `context_used` field's own post-hoc overwrite above.
    hallucination: Any = Field(
        default=None,
        description="Post-generation hallucination/groundedness check (agents.hallucination_agent). "
                    "None when no answer was actually generated to check (e.g. no context retrieved).",
    )


def _groundedness_label(hallucination_score: int) -> str:
    """Buckets the hallucination agent's continuous 0-100 score into the
    High/Medium/Low label the UI displays. 100=fully hallucinated in that
    scale, so groundedness is its inverse."""
    if hallucination_score <= 20:
        return "High"
    if hallucination_score <= 50:
        return "Medium"
    return "Low"


def _run_hallucination_check(question: str, context_str: str, answer: str) -> Dict[str, Any]:
    """Post-processing validation step only — never touches retrieval,
    embeddings, reranking, or the answer itself. Failures here must never
    prevent the answer from being returned, so every exception is caught
    here rather than left to propagate into answer_legal_question's own
    try/except (which would otherwise mistake a hallucination-check failure
    for a QA generation failure and replace the real answer with an error)."""
    try:
        evaluation = evaluate_hallucination(question=question, context=context_str, answer=answer)
        payload = {
            "hallucination_score": evaluation.hallucination_score,
            "trust_score": evaluation.trust_score,
            "confidence": evaluation.confidence_score,
            "groundedness": _groundedness_label(evaluation.hallucination_score),
            "citation_quality": evaluation.citation_quality,
            "unsupported_statements": evaluation.unsupported_statements,
        }
        logger.debug(f"[qa_agent] final hallucination values sent to UI: {payload}")
        return payload
    except Exception:
        logger.exception("Hallucination check failed (non-fatal, answer is unaffected)")
        return {
            "hallucination_score": None,
            "trust_score": None,
            "confidence": None,
            "groundedness": None,
            "citation_quality": None,
            "unsupported_statements": [],
            "error": "Hallucination Check Failed",
        }


def answer_legal_question(query: str, doc_id: Optional[str] = None) -> QAResult:
    """Legal Question Answering Agent.

    Query -> Embedding -> Vector Search (Top 5) -> optional Cross-Encoder
    Reranker -> Prompt Builder -> single LLM call -> Answer + citations.
    """
    retrieved_docs = perform_vector_search(query, doc_id, k=5)

    retrieved_chunk_ids = [d.metadata.get("clause_id") for d in retrieved_docs if d.metadata.get("clause_id") is not None]
    try:
        crud.log_retrieval(query_text=query, doc_id_scope=doc_id, retrieved_chunk_ids=retrieved_chunk_ids)
    except Exception:
        logger.exception("Failed to log retrieval history (non-fatal)")

    if not retrieved_docs:
        return QAResult(
            answer="I could not find any relevant information in the documents to answer your question.",
            supporting_clauses=[], citation_references=[], confidence_score=0,
        )

    context_str = build_prompt_context(retrieved_docs)

    system_instruction = (
        "You are an expert corporate legal counsel. "
        "Answer the user's question using strictly the provided context blocks. "
        "Do not hallucinate or use outside knowledge. If the answer is not in the context, say so clearly. "
        "Provide a comprehensive 'answer', 'supporting_clauses' texts, 'citation_references' with document IDs and section names, "
        "and a 'confidence_score' (0-100)."
    )
    prompt = f"Retrieved Context:\n{context_str}\n\nUser Question:\n{query}"

    try:
        result = invoke_llm_structured(system_instruction, prompt, QAResult)
        result.context_used = context_str
        result.hallucination = _run_hallucination_check(query, context_str, result.answer)
        return result
    except Exception as e:
        logger.error(f"QA generation failed: {e}")
        return QAResult(
            answer=f"An error occurred while generating the answer: {e}",
            supporting_clauses=[], citation_references=[], confidence_score=0,
        )
