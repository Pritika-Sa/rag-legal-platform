"""Pure-Python lexical/vector fusion for retrieval — no LLM involved.

BM25 (rank_bm25) supplies an exact-term-match signal that dense embeddings
under-weight (e.g. "Section 8.2", "liquidated damages"). Reciprocal Rank
Fusion (RRF) combines it with the existing vector-similarity ranking
without needing the two scores to be on comparable scales.
"""

import re
from typing import List

from rank_bm25 import BM25Okapi

_TOKEN_RE = re.compile(r"[a-z0-9]+")

DEFAULT_K_RRF = 60


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def fuse_vector_and_bm25(query: str, pool: List, k_rrf: int = DEFAULT_K_RRF) -> List:
    """`pool` is already vector-similarity ordered (index 0 = most similar).
    Builds a BM25 index scoped to just this pool (cheap — typically <=20
    documents), ranks the same pool by BM25, then fuses both rankings via
    Reciprocal Rank Fusion (k_rrf=60 is the standard literature default).
    Returns the pool reordered by fused score, highest first."""
    if not pool:
        return []
    if len(pool) == 1:
        return list(pool)

    corpus_tokens = [_tokenize(doc.page_content) for doc in pool]
    bm25 = BM25Okapi(corpus_tokens)
    bm25_scores = bm25.get_scores(_tokenize(query))
    bm25_rank_order = sorted(range(len(pool)), key=lambda i: bm25_scores[i], reverse=True)
    bm25_rank_of = {doc_idx: rank for rank, doc_idx in enumerate(bm25_rank_order)}

    fused = []
    for vector_rank, doc in enumerate(pool):
        bm25_rank = bm25_rank_of[vector_rank]
        score = 1.0 / (k_rrf + vector_rank) + 1.0 / (k_rrf + bm25_rank)
        fused.append((doc, score))

    fused.sort(key=lambda pair: pair[1], reverse=True)
    return [doc for doc, _score in fused]
