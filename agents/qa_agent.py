import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agents.hallucination_agent import evaluate_hallucination
from database import crud
from services.aggregate_metrics_service import answer_aggregate_metric, classify_aggregate_metric
from services.retrieval_service import build_prompt_context, perform_vector_search
from utils.llm_client import invoke_llm_structured

logger = logging.getLogger(__name__)

OUT_OF_SCOPE_MESSAGE = (
    "This question is not related to the active document. "
    "Legal AI can answer only questions based on the active document."
)


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


def _is_out_of_scope_answer(answer: str) -> bool:
    """Recognize the model's former vague refusal and replace it with the
    active-document guidance shown to the user."""
    normalized = answer.strip().lower().rstrip(".! ")
    return normalized in {"not applicable", "not relevant", "n/a"}


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


def answer_legal_question(query: str, doc_id: Optional[str] = None, user_id: Optional[Any] = None) -> QAResult:
    """Legal Question Answering Agent.

    Question Classifier -> [Aggregate Document Metric -> MongoDB] or
    [Legal Question -> Query -> Embedding -> Vector Search (Top 5) ->
    optional Cross-Encoder Reranker -> Prompt Builder -> single LLM call] ->
    Answer + citations.

    The classifier (services.aggregate_metrics_service) only ever short-
    circuits questions asking for a number/label that's already persisted
    on the document (clause count, risk/authenticity scores, contradiction
    count, ...) — those are answered straight from MongoDB, never estimated
    by the LLM from a handful of retrieved chunks. Everything else (clause
    explanations, summaries, comparisons) falls through to the RAG pipeline
    below completely unchanged.

    `user_id` is the authenticated caller's id and is mandatory: it scopes
    retrieval to that user's own documents (see
    services.retrieval_service.perform_vector_search /
    vectorstore.chroma_client.search_document), which is what prevents one
    user's uploaded documents from being retrieved into another user's
    answer context.
    """
    metric = classify_aggregate_metric(query)
    if metric is not None:
        aggregate_answer = answer_aggregate_metric(metric, doc_id, user_id)
        if aggregate_answer is not None:
            return QAResult(
                answer=aggregate_answer,
                supporting_clauses=[], citation_references=[], confidence_score=100,
            )
        # No active document to scope the metric to (or it didn't resolve to
        # a real, owned document) — fall through to the RAG pipeline, same
        # as any other question, rather than inventing a separate error path.

    retrieved_docs = perform_vector_search(query, doc_id, user_id=user_id, k=5)

    retrieved_chunk_ids = [d.metadata.get("clause_id") for d in retrieved_docs if d.metadata.get("clause_id") is not None]
    try:
        crud.log_retrieval(query_text=query, doc_id_scope=doc_id, retrieved_chunk_ids=retrieved_chunk_ids)
    except Exception:
        logger.exception("Failed to log retrieval history (non-fatal)")

    if not retrieved_docs:
        return QAResult(
            answer=OUT_OF_SCOPE_MESSAGE,
            supporting_clauses=[], citation_references=[], confidence_score=0,
        )

    context_str = build_prompt_context(retrieved_docs)

    system_instruction = (
        "You are an expert corporate legal counsel. "
        "Answer the user's question using strictly the provided context blocks. "
        "Do not hallucinate or use outside knowledge. If the query is unrelated to the active document or cannot be "
        "answered from its context, respond exactly: 'This question is not related to the active document. Legal AI "
        "can answer only questions based on the active document.' Never respond with 'Not applicable'. "
        "Provide a comprehensive 'answer', 'supporting_clauses' texts, 'citation_references' with document IDs and section names, "
        "and a 'confidence_score' (0-100)."
    )
    prompt = f"Retrieved Context:\n{context_str}\n\nUser Question:\n{query}"

    try:
        result = invoke_llm_structured(system_instruction, prompt, QAResult)
        if _is_out_of_scope_answer(result.answer):
            return QAResult(
                answer=OUT_OF_SCOPE_MESSAGE,
                supporting_clauses=[], citation_references=[], confidence_score=0,
            )
        result.context_used = context_str
        result.hallucination = _run_hallucination_check(query, context_str, result.answer)
        return result
    except Exception as e:
        logger.error(f"QA generation failed: {e}")
        return QAResult(
            answer=f"An error occurred while generating the answer: {e}",
            supporting_clauses=[], citation_references=[], confidence_score=0,
        )
