"""Centralized retrieval service (Stage 3, no LLM): every module that needs
grounded context goes through this file rather than querying ChromaDB or
building context strings itself.

Pipeline: vector similarity search (top-k) -> optional BGE cross-encoder
rerank -> prompt context assembly. Deliberately minimal (no intent-based
metadata filtering, no BM25/RRF fusion, no sentence-level compression) so a
query costs one ANN lookup and at most one small cross-encoder pass, keeping
QA latency low.
"""

import logging
import os
from typing import List, Optional

from dotenv import load_dotenv

from services.prompt_builder import build_context_block
from utils.reranker import rerank_documents
from vectorstore import chroma_client

load_dotenv()
logger = logging.getLogger(__name__)

# When enabled, a larger candidate pool is pulled from the vector store and
# narrowed to `k` by the BGE cross-encoder; when disabled, the vector
# store's own top-k is returned directly (one ANN query, no reranker
# load/inference) for the lowest-latency path.
RERANK_ENABLED = os.getenv("QA_RERANK_ENABLED", "true").strip().lower() in ("1", "true", "yes")
RERANK_CANDIDATE_POOL = int(os.getenv("QA_RERANK_CANDIDATE_POOL", "20"))


def perform_vector_search(
    query: str, doc_id: Optional[str] = None, k: int = 5, use_reranker: Optional[bool] = None
) -> List:
    """Query Embedding -> Vector Search (Top-K) -> optional Cross-Encoder Reranker.

    `use_reranker=None` defers to the QA_RERANK_ENABLED env var; pass
    True/False to override for a specific call.
    """
    rerank = RERANK_ENABLED if use_reranker is None else use_reranker

    if not rerank:
        return chroma_client.search_document(query, document_id=doc_id, k=k)

    candidate_pool = chroma_client.search_document(query, document_id=doc_id, k=RERANK_CANDIDATE_POOL)
    if not candidate_pool:
        return []
    reranked = rerank_documents(query, candidate_pool, top_k=k)
    return [doc for doc, score in reranked]


def build_prompt_context(chunks: list) -> str:
    """Formats retrieved chunks (full clause text, uncompressed) into the
    citation-friendly context block consumed by the QA prompt."""
    blocks = [(doc.metadata, doc.page_content.strip()) for doc in chunks]
    return build_context_block(blocks)
