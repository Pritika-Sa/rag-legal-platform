"""Assembles the explainability contract: per-clause confidence and the
per-dimension evidence breakdown. Because LRSI is an additive weighted sum
(fusion.lrsi_scores), each dimension's contribution to the final score is
exactly `weight * score * 100` — no post-hoc attribution technique (SHAP,
LIME) is needed to explain the fusion layer itself; this module just
assembles that arithmetic into a readable object.
"""

import statistics
from typing import Dict, List, Optional, Tuple

import numpy as np

from risk_engine import fusion
from risk_engine.dimensions import feature_evidence
from risk_engine.schemas import DimensionScore, LegalFeatureVector

_CONFIDENCE_COMPONENT_NAMES = ["agreement", "feature_confidence", "margin"]


def _confidence_components(
    feature_signals: Dict[str, float],
    semantic_signals: Dict[str, float],
    feature_confidences: List[float],
) -> Tuple[float, float, float]:
    """The three raw ingredients of a clause's confidence score, each in
    [0,1] — see compute_confidence_scores for how they're combined.

    agreement: 1 - mean_d|F_d - E_d| — the two independently-computed
    signals disagreeing is itself informative and should lower confidence,
    not be silently averaged away.

    feature_confidence: mean confidence of every extracted feature feeding
    this clause (defaults to 0.5, "unknown," when nothing was extracted at
    all) — see agents/feature_extraction_agent.py's _evidence_confidence
    for how those per-feature values themselves are computed.

    margin: gap between the clause's strongest and second-strongest
    semantic-dimension signal — a clause whose meaning clearly picks one
    dominant risk dimension is scored more confidently than one sitting
    ambiguously between two.
    """
    dims = list(feature_signals.keys())
    disagreement = statistics.mean(abs(feature_signals[d] - semantic_signals[d]) for d in dims)
    agreement = 1.0 - disagreement
    avg_feature_conf = statistics.mean(feature_confidences) if feature_confidences else 0.5

    sorted_semantic = sorted(semantic_signals.values(), reverse=True)
    margin = (sorted_semantic[0] - sorted_semantic[1]) if len(sorted_semantic) > 1 else 0.5

    return agreement, avg_feature_conf, margin


def compute_confidence_scores(
    feature_signals_per_clause: List[Dict[str, float]],
    semantic_signals_per_clause: List[Dict[str, float]],
    feature_confidences_per_clause: List[List[float]],
) -> Tuple[List[float], Dict[str, float]]:
    """Batch confidence computation for every clause in a document.
    Combines each clause's (agreement, feature_confidence, margin) triple
    into a single 0-100 score, weighting the three components by
    risk_engine.fusion.entropy_weights instead of a fixed split — the same
    "which signal actually varies, and is therefore informative, across
    this document's clauses" principle already used for the between-
    dimension LRSI weights and the within-dimension alpha coefficients
    (fusion.dynamic_alpha), applied a third time here instead of a
    hand-picked 0.4/0.3/0.3.

    Batch, not per-clause, for the same reason those two are: entropy
    weighting is inherently a statistic over a distribution, and a single
    clause has no distribution to compute one from.

    Returns (confidence_per_clause, weights_used) — the weights are meant
    to be surfaced on the caller's output (see
    DocumentRiskAssessment.confidence_weights) rather than kept as a
    hidden internal, consistent with dimension_weights/dimension_alphas.
    """
    components = [
        _confidence_components(f, s, fc)
        for f, s, fc in zip(feature_signals_per_clause, semantic_signals_per_clause, feature_confidences_per_clause)
    ]
    matrix = np.array(components, dtype=float)
    weights_vec = fusion.entropy_weights(matrix)
    raw_scores = 100.0 * (matrix @ weights_vec)
    confidence_per_clause = [float(max(0.0, min(100.0, s))) for s in raw_scores]
    weights = dict(zip(_CONFIDENCE_COMPONENT_NAMES, weights_vec.tolist()))
    return confidence_per_clause, weights


def build_dimension_breakdown(
    feature_signals: Dict[str, float],
    semantic_signals: Dict[str, float],
    alphas: Dict[str, float],
    fused_scores: Dict[str, float],
    weights: Dict[str, float],
    fv: LegalFeatureVector,
    semantic_evidence: Dict[str, Optional[Tuple[str, float]]],
) -> List[DimensionScore]:
    """Ranked (largest contribution first) per-dimension breakdown — the
    'why is this clause risky' half of the explainability contract.
    `alphas` is the per-dimension feature/semantic trust coefficient
    actually used for this document (risk_engine.fusion.dynamic_alpha) —
    surfaced here so it's visible in the same place as everything else that
    went into the score, not a hidden internal."""
    breakdown = []
    for dimension in fused_scores:
        proto = semantic_evidence.get(dimension)
        breakdown.append(DimensionScore(
            dimension=dimension,
            feature_signal=feature_signals[dimension],
            semantic_signal=semantic_signals[dimension],
            alpha=alphas[dimension],
            score=fused_scores[dimension],
            weight=weights[dimension],
            contribution=round(weights[dimension] * fused_scores[dimension] * 100, 2),
            feature_evidence=feature_evidence(fv, dimension),
            semantic_evidence={"prototype": proto[0], "similarity": round(proto[1], 4)} if proto else None,
        ))
    breakdown.sort(key=lambda d: d.contribution, reverse=True)
    return breakdown
