import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

from agents.rule_engine import detect_query_intent
from database import crud
from utils.hybrid_search import fuse_vector_and_bm25
from utils.llm_client import invoke_llm_structured
from utils.reranker import rerank_documents
from vectorstore import chroma_client

logger = logging.getLogger(__name__)

MAX_LQ_RAG_ITERATIONS = 3
TRUST_THRESHOLD = 70
CANDIDATE_POOL_SIZE = 20
FUSED_POOL_SIZE = 15
MAX_SENTENCES_PER_CHUNK = 3

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "of", "to", "in",
    "on", "for", "and", "or", "this", "that", "what", "which", "who", "how",
    "does", "do", "did", "shall", "will", "with", "as", "by", "at", "it", "its",
}


def _content_terms(text: str) -> set:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


class RetrievalState(TypedDict):
    """Documents the shape of data as it flows through the retrieval
    helpers below. Not an executable LangGraph — the audit-refinement loop
    further down is a simple bounded retry with no branching, so a full
    StateGraph would add indirection without new capability. This TypedDict
    exists purely so the pipeline's stages are typed and inspectable."""
    query: str
    document_id: Optional[str]
    intent_filter: Dict[str, Any]
    candidate_pool: List[Any]       # vector-ranked Chroma Documents, size <= CANDIDATE_POOL_SIZE
    fused_pool: List[Any]           # after BM25 + RRF fusion, size <= CANDIDATE_POOL_SIZE
    reranked_chunks: List[Any]      # after BGE cross-encoder, size <= k (small, not full documents)
    compressed_context: str         # after compress_context — sentence-trimmed, small


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


def perform_hybrid_search(query: str, doc_id: Optional[str] = None, k: int = 5) -> List:
    """Metadata-aware hybrid retrieval (Stage 3, no LLM):
    intent detection → metadata-filtered vector search → BM25+RRF fusion →
    BGE cross-encoder rerank. Never searches the full collection blindly —
    the metadata filter narrows the candidate pool *before* vector search
    when the query names a specific clause type, falling back to an
    unfiltered search if that returns nothing (so generic questions like
    "summarize this contract" are never made worse by a wrong guess)."""
    intent_filter = detect_query_intent(query)

    candidate_pool = chroma_client.search_document(
        query, document_id=doc_id, filters=intent_filter or None, k=CANDIDATE_POOL_SIZE
    )
    if not candidate_pool and intent_filter:
        logger.info("Metadata-filtered search returned 0 results; retrying without the clause_type filter.")
        candidate_pool = chroma_client.search_document(query, document_id=doc_id, k=CANDIDATE_POOL_SIZE)

    if not candidate_pool:
        return []

    fused_pool = fuse_vector_and_bm25(query, candidate_pool)
    reranked = rerank_documents(query, fused_pool[:FUSED_POOL_SIZE], top_k=k)
    return [doc for doc, score in reranked]


def _score_sentence(query_terms: set, sentence: str) -> float:
    """Overlap-coefficient-style score: how many non-stopword query terms
    appear in the sentence, normalized by sqrt(sentence length) so long
    sentences don't win purely by containing more words overall."""
    sentence_terms = _content_terms(sentence)
    if not sentence_terms:
        return 0.0
    overlap = len(query_terms & sentence_terms)
    return overlap / (len(sentence_terms) ** 0.5)


def _is_near_duplicate(candidate: str, kept: List[str], threshold: float = 0.9) -> bool:
    return any(SequenceMatcher(None, candidate, k).ratio() > threshold for k in kept)


def compress_context(query: str, chunks: list, max_sentences_per_chunk: int = MAX_SENTENCES_PER_CHUNK) -> str:
    """Python-only context compression (Stage 3, no LLM): keeps only the
    top query-relevant, non-duplicate sentences from each retrieved chunk,
    in original order, instead of sending each chunk's full text. This
    replaces blind hard-truncation (utils/llm_client.py's
    _fit_prompt_to_budget only cuts from the end with no relevance
    awareness) with a relevance-aware trim applied before the prompt is
    even built."""
    query_terms = _content_terms(query)
    context_str = ""
    for idx, doc in enumerate(chunks):
        meta = doc.metadata
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(doc.page_content.strip()) if s.strip()]
        scored = [(i, s, _score_sentence(query_terms, s)) for i, s in enumerate(sentences)]
        scored.sort(key=lambda item: item[2], reverse=True)

        kept_indices: List[int] = []
        kept_texts: List[str] = []
        for i, s, score in scored:
            if len(kept_indices) >= max_sentences_per_chunk:
                break
            if score == 0:
                continue
            if _is_near_duplicate(s, kept_texts):
                continue
            kept_indices.append(i)
            kept_texts.append(s)

        if not kept_indices and sentences:
            # Every sentence scored 0 (pure boilerplate chunk) — keep the
            # first sentence so the chunk isn't silently dropped entirely.
            kept_indices = [0]

        ordered = [sentences[i] for i in sorted(kept_indices)]
        compressed_block = " ".join(ordered)

        context_str += (
            f"--- Context Block {idx+1} "
            f"(Doc ID: {meta.get('document_id', meta.get('doc_id'))}, "
            f"Section: {meta.get('clause_type', 'Unknown')}) ---\n"
            f"{compressed_block}\n\n"
        )
    return context_str


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
