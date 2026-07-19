"""HybridExplainableRiskEngine — the default RiskEngine implementation, and
the complete replacement for agents/rule_engine.score_risk_points() /
RISK_PHRASE_POINTS. Fuses a corpus-relative structured-feature signal with
a legal-embedding semantic signal per dimension (risk_engine.dimensions),
combines the five dimensions into one LRSI per clause using entropy-derived
weights (risk_engine.fusion), classifies Low/Medium/High against Jenks
natural-breaks cut points computed from this installation's own score
history once there's enough of it (risk_engine.thresholds), and assembles
the explainability contract (risk_engine.explain) — with no manually
assigned weight or threshold anywhere in the path. The same entropy-
weighting principle is applied three times over, at three different
granularities: across the 5 risk dimensions (dimension_weights), within
each dimension's feature/semantic fusion (dimension_alphas), and across
the three ingredients of a clause's confidence score (confidence_weights).
"""

from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from risk_engine.base import RiskEngine
from risk_engine.dimensions import DIMENSIONS, PROTOTYPE_DIMENSIONS, ambiguity_outlier_signal, compute_feature_signals
from risk_engine.explain import build_dimension_breakdown, compute_confidence_scores
from risk_engine import fusion
from risk_engine.prototype_store import PrototypeStore
from risk_engine.schemas import ClauseInput, DocumentRiskAssessment, RiskAssessment
from risk_engine.thresholds import DEFAULT_CLAUSE_CUTS


class HybridExplainableRiskEngine(RiskEngine):
    def __init__(
        self,
        embed_fn: Callable[[List[str]], np.ndarray],
        alpha: Optional[Dict[str, float]] = None,
        get_clause_thresholds: Optional[Callable[[], Tuple[float, float]]] = None,
    ):
        """`embed_fn` is injected rather than imported directly so this
        class never depends on a specific embedding backend and never
        forces a model download in unit tests — production callers pass
        services.semantic_similarity.embed_texts (or a legal-domain
        equivalent once EMBEDDING_MODEL is repointed, see the design doc's
        Embedding workflow section).

        `alpha` overrides the per-dimension feature/semantic trust
        coefficient (risk_engine.fusion.fuse_signal) for any dimension
        named in it — e.g. once labeled data exists and a dimension's
        coefficient has been fit by regression (see base.py and the design
        doc's supervised-model swap path). Any dimension *not* named here
        gets fusion.dynamic_alpha()'s per-document, entropy-derived value
        instead of a fixed constant — this is the default for every
        dimension when `alpha` is omitted entirely.

        `get_clause_thresholds` is called fresh on every score_document()
        (not just once at construction) so a caller can back it with a
        risk_engine.thresholds.ThresholdRegistry and have a later
        recalibration take effect immediately, without rebuilding this
        engine (and re-embedding every prototype sentence) just to pick up
        new cut points. Defaults to the fixed cold-start cuts.
        """
        self._embed_fn = embed_fn
        self._alpha_overrides = alpha or {}
        self._get_clause_thresholds = get_clause_thresholds or (lambda: DEFAULT_CLAUSE_CUTS)
        self._prototypes = PrototypeStore(embed_fn)

    def score_document(self, clauses: List[ClauseInput]) -> DocumentRiskAssessment:
        if not clauses:
            return DocumentRiskAssessment(
                clause_assessments=[],
                dimension_weights={d: 1.0 / len(DIMENSIONS) for d in DIMENSIONS},
                average_lrsi=0.0, document_risk_score=0.0,
                high_count=0, medium_count=0, low_count=0,
            )

        feature_vectors = [c.features for c in clauses]
        feature_signals = compute_feature_signals(feature_vectors)  # {dim: [F_d per clause]}

        embeddings = np.asarray(self._embed_fn([c.text for c in clauses]))
        semantic_signals: Dict[str, List[float]] = {d: [] for d in DIMENSIONS}
        semantic_evidence_per_clause: List[Dict[str, Optional[tuple]]] = [dict() for _ in clauses]

        for dimension in PROTOTYPE_DIMENSIONS:
            for i, emb in enumerate(embeddings):
                sim, prototype_sentence = self._prototypes.max_similarity(dimension, emb)
                semantic_signals[dimension].append(sim)
                semantic_evidence_per_clause[i][dimension] = (prototype_sentence, sim)

        semantic_signals["Ambiguity"] = ambiguity_outlier_signal(embeddings)
        for i in range(len(clauses)):
            semantic_evidence_per_clause[i]["Ambiguity"] = None  # outlier score has no prototype sentence

        # alpha is a document-level statistic per dimension (like the
        # between-dimension weights below), not a per-clause value: how
        # much this document's own F_d/E_d spread favors one branch over
        # the other, computed once and applied uniformly across every
        # clause in this document.
        alphas: Dict[str, float] = {
            d: self._alpha_overrides.get(d) if d in self._alpha_overrides
            else fusion.dynamic_alpha(np.array(feature_signals[d]), np.array(semantic_signals[d]))
            for d in DIMENSIONS
        }

        fused: Dict[str, List[float]] = {
            d: [fusion.fuse_signal(feature_signals[d][i], semantic_signals[d][i], alphas[d])
                for i in range(len(clauses))]
            for d in DIMENSIONS
        }

        score_matrix = np.array([[fused[d][i] for d in DIMENSIONS] for i in range(len(clauses))])
        weights_vec = fusion.entropy_weights(score_matrix)
        weights = dict(zip(DIMENSIONS, weights_vec.tolist()))
        lrsi_values = fusion.lrsi_scores(score_matrix, weights_vec)
        low_medium_cut, medium_high_cut = self._get_clause_thresholds()

        per_clause_f = [{d: feature_signals[d][i] for d in DIMENSIONS} for i in range(len(clauses))]
        per_clause_s = [{d: semantic_signals[d][i] for d in DIMENSIONS} for i in range(len(clauses))]
        per_clause_feature_conf = [
            [o.confidence for o in clause.features.obligations]
            + [a.confidence for a in clause.features.legal_actions]
            + [e.confidence for e in clause.features.entities]
            for clause in clauses
        ]
        confidences, confidence_weights = compute_confidence_scores(
            per_clause_f, per_clause_s, per_clause_feature_conf,
        )

        assessments: List[RiskAssessment] = []
        for i, clause in enumerate(clauses):
            fused_i = {d: fused[d][i] for d in DIMENSIONS}
            breakdown = build_dimension_breakdown(
                per_clause_f[i], per_clause_s[i], alphas, fused_i, weights,
                clause.features, semantic_evidence_per_clause[i],
            )
            lrsi = float(lrsi_values[i])
            assessments.append(RiskAssessment(
                clause_id=clause.clause_id,
                lrsi=round(lrsi, 2),
                classification=fusion.classify(lrsi, low_medium_cut, medium_high_cut),
                confidence=round(confidences[i], 2),
                dimension_breakdown=breakdown,
            ))

        classes = [a.classification for a in assessments]
        return DocumentRiskAssessment(
            clause_assessments=assessments,
            dimension_weights={k: round(v, 4) for k, v in weights.items()},
            dimension_alphas={k: round(v, 4) for k, v in alphas.items()},
            confidence_weights={k: round(v, 4) for k, v in confidence_weights.items()},
            average_lrsi=round(float(np.mean(lrsi_values)), 2),
            document_risk_score=round(fusion.document_risk_score(lrsi_values), 2),
            high_count=classes.count("High"),
            medium_count=classes.count("Medium"),
            low_count=classes.count("Low"),
        )
