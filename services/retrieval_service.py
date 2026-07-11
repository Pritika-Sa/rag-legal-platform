"""Centralized retrieval service (Stage 3, no LLM): every module that needs
grounded context goes through this file rather than querying ChromaDB or
building context strings itself.

Pipeline: intent detection -> metadata-filtered vector search -> BM25+RRF
fusion -> BGE cross-encoder rerank -> sentence-level compression. Extracted
out of agents/qa_agent.py so other modules (dashboard insights, audits,
future features) can share the exact same retrieval path instead of each
re-implementing it.
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, TypedDict

from agents.rule_engine import detect_query_intent
from services.prompt_builder import build_context_block
from utils.hybrid_search import fuse_vector_and_bm25
from utils.reranker import rerank_documents
from vectorstore import chroma_client

logger = logging.getLogger(__name__)

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
    in qa_agent.py is a simple bounded retry with no branching, so a full
    StateGraph would add indirection without new capability. This TypedDict
    exists purely so the pipeline's stages are typed and inspectable."""
    query: str
    document_id: Optional[str]
    intent_filter: Dict[str, Any]
    candidate_pool: List[Any]       # vector-ranked Chroma Documents, size <= CANDIDATE_POOL_SIZE
    fused_pool: List[Any]           # after BM25 + RRF fusion, size <= CANDIDATE_POOL_SIZE
    reranked_chunks: List[Any]      # after BGE cross-encoder, size <= k (small, not full documents)
    compressed_context: str         # after compress_context — sentence-trimmed, small


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
    blocks: List[Any] = []
    for doc in chunks:
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
        blocks.append((meta, compressed_block))

    return build_context_block(blocks)
