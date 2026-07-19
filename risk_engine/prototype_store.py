"""Loads risk_engine/prototypes.json — natural-language dimension
descriptions, the direct replacement for the deleted keyword-weight tables
(rules/risk_rules.json, escalation_rules.json, mitigation_rules.json) — and
embeds every sentence once via an injected embedding function. A
dimension's semantic signal E_d for a clause is the clause embedding's
maximum cosine similarity to any of that dimension's prototype sentences,
so "Liability shall be without limit" and "There is no cap on damages"
score similarly against the Financial prototypes despite sharing no
substring, which is the whole point of moving off keyword matching.
"""

import json
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np

from services.semantic_similarity import cosine_similarity_matrix

_PROTOTYPES_PATH = Path(__file__).resolve().parent / "prototypes.json"


class PrototypeStore:
    def __init__(self, embed_fn: Callable[[List[str]], np.ndarray], prototypes_path: Path = _PROTOTYPES_PATH):
        with prototypes_path.open(encoding="utf-8") as f:
            self._prototypes: Dict[str, List[str]] = json.load(f)
        self._embeddings: Dict[str, np.ndarray] = {
            dimension: np.asarray(embed_fn(sentences)) for dimension, sentences in self._prototypes.items()
        }

    def dimensions(self) -> List[str]:
        return list(self._prototypes.keys())

    def max_similarity(self, dimension: str, clause_embedding: np.ndarray) -> Tuple[float, str]:
        """Returns (similarity, matched_prototype_sentence) — the matched
        sentence becomes the clause's semantic evidence for this dimension."""
        proto_vectors = self._embeddings[dimension]
        sims = cosine_similarity_matrix(np.asarray(clause_embedding).reshape(1, -1), proto_vectors)[0]
        idx = int(np.argmax(sims))
        return float(sims[idx]), self._prototypes[dimension][idx]
