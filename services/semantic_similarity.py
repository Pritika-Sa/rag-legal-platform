"""Shared embedding/similarity primitives for agents that need to compare
clauses by meaning rather than exact wording (contradiction_agent.py,
comparison_agent.py). Uses the same embedding model already loaded for the
Chroma vector store (utils/llm_client.get_embeddings) so no second model is
loaded into memory.
"""

import numpy as np

from utils.llm_client import get_embeddings


def embed_texts(texts: list) -> np.ndarray:
    """Embeds a list of texts, returning an (n, dim) float array. Returns an
    empty (0, 0) array for an empty input instead of erroring."""
    if not texts:
        return np.zeros((0, 0))
    vectors = get_embeddings().embed_documents(texts)
    return np.array(vectors, dtype=float)


def cosine_similarity_matrix(vectors_a: np.ndarray, vectors_b: np.ndarray) -> np.ndarray:
    """Pairwise cosine similarity between two sets of vectors, shape
    (len(vectors_a), len(vectors_b)). Normalizes defensively even though
    get_embeddings() already returns unit-normalized vectors, so this stays
    correct if that ever changes."""
    if vectors_a.size == 0 or vectors_b.size == 0:
        return np.zeros((len(vectors_a), len(vectors_b)))
    a_norm = vectors_a / np.clip(np.linalg.norm(vectors_a, axis=1, keepdims=True), 1e-9, None)
    b_norm = vectors_b / np.clip(np.linalg.norm(vectors_b, axis=1, keepdims=True), 1e-9, None)
    return a_norm @ b_norm.T
