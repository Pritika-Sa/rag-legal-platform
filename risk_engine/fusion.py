"""Fusion math: per-dimension signal combination, entropy-derived dimension
weighting, and the Legal Risk Severity Index itself. This module is the
entire answer to "where do the weights come from" — nowhere in this file is
a weight read from a table or typed in by a person; every weight is a
statistic computed from the score distribution actually observed in the
document being scored.
"""

import math
from typing import List

import numpy as np

DEFAULT_LOW_MEDIUM_CUT = 35.0
DEFAULT_MEDIUM_HIGH_CUT = 70.0


def fuse_signal(feature_signal: float, semantic_signal: float, alpha: float = 0.5) -> float:
    """S_d(c) = clamp(alpha*F_d + (1-alpha)*E_d, 0, 1).

    The design proposal describes this fusion as a logistic squash of the
    convex combination. Since F_d and E_d are both already bounded in
    [0,1], their convex combination is too, and an additional sigmoid would
    compress every score toward 0.5 instead of preserving the full 0-100
    LRSI range — so a clamp (equivalent numerical-safety guarantee, no
    compression) is used here instead.

    `alpha` is a per-dimension feature/semantic trust coefficient, not a
    risk-magnitude weight — see dynamic_alpha() below for how
    hybrid_engine.HybridExplainableRiskEngine computes it per document
    (falling back to 0.5, equal trust, only when there's too little data
    to tell the two branches apart).
    """
    return max(0.0, min(1.0, alpha * feature_signal + (1.0 - alpha) * semantic_signal))


def _raw_entropy_weights(score_matrix: np.ndarray, epsilon: float) -> np.ndarray:
    n, m = score_matrix.shape
    shifted = score_matrix + epsilon
    col_sums = shifted.sum(axis=0)
    p = shifted / col_sums
    k = 1.0 / math.log(n)
    plogp = np.where(p > 0, p * np.log(p), 0.0)
    e = -k * plogp.sum(axis=0)
    d = (1.0 - e) + epsilon
    return d / d.sum()


def entropy_weights(score_matrix: np.ndarray, epsilon: float = 1e-4, shrinkage_n0: float = 10.0) -> np.ndarray:
    """Entropy Weight Method (Shannon entropy applied to objective criteria
    weighting; Zeleny, 1982) over an (n_clauses, n_dimensions) matrix of
    S_d values in [0,1]. Returns weights summing to 1 — a dimension whose
    scores vary a lot across this document's clauses (high discriminative
    power) earns more influence on the final LRSI automatically; a
    dimension that scores nearly the same for every clause carries little
    information and is down-weighted, again automatically.

    n<2: entropy is undefined for a single observation (the normalizing
    constant k=1/ln(n) is singular at n=1) — falls back to equal weights,
    the only defensible default when there is no distribution to compare
    against.

    `epsilon` is a fixed numerical-stability floor, not a per-dimension
    tuned weight: it avoids log(0) and keeps a zero-variance dimension from
    being assigned literally zero influence (standard EWM smoothing
    practice), rather than encoding any belief about that dimension's
    importance.

    Shrinkage toward equal weights at small n: EWM is well known in the
    MCDM literature to be volatile on small samples — with only 3-5
    clauses, a single clause that happens to be a semantic outlier on one
    dimension can swing that dimension's entire weight share, exactly the
    kind of instability a peer reviewer (or a user staring at a mis-ranked
    clause) would flag. `lam = n / (n + shrinkage_n0)` blends the raw EWM
    weights with the uniform prior (1/m each), trusting the data-derived
    weights more as the clause sample grows and falling back toward
    "trust every dimension equally" when it's small — the same shrinkage
    principle behind empirical-Bayes/credibility-theory estimators, not a
    per-dimension tuned constant: `shrinkage_n0` (the sample size at which
    the blend is 50/50) is a single, disclosed, ablatable global constant,
    identical in kind to `concentration_lambda` in document_risk_score.
    """
    n, m = score_matrix.shape
    if n < 2:
        return np.full(m, 1.0 / m)

    raw = _raw_entropy_weights(score_matrix, epsilon)
    lam = n / (n + shrinkage_n0)
    equal = np.full(m, 1.0 / m)
    return lam * raw + (1.0 - lam) * equal


def dynamic_alpha(feature_signals: np.ndarray, semantic_signals: np.ndarray,
                   epsilon: float = 1e-4, shrinkage_n0: float = 10.0) -> float:
    """Per-dimension feature/semantic trust coefficient (`alpha` in
    fuse_signal), computed the same way entropy_weights decides how much
    each of the 5 risk dimensions matters — applied one level down, to the
    two signals *within* a single dimension instead of across dimensions.

    Builds a 2-column [F_d, E_d] matrix from this document's clauses and
    runs entropy_weights on it: whichever branch varies more across this
    document's clauses (more discriminative for this specific document)
    earns more trust automatically, exactly the same "goodness of variance
    fit" logic as the between-dimension weights, not a second hand-picked
    constant. Small-n shrinkage (already inside entropy_weights) means a
    short document — or a dimension where both branches happen to look
    alike — recovers close to the original fixed 0.5 (equal trust) rather
    than swinging on a handful of points.

    Inputs are clamped to [0,1] before use: E_d is a cosine similarity or
    1-minus-similarity and could in principle dip slightly negative, which
    would break entropy_weights' epsilon-shift (it assumes non-negative
    values, like every other score this module works with).
    """
    matrix = np.clip(np.column_stack([feature_signals, semantic_signals]), 0.0, 1.0)
    weights = entropy_weights(matrix, epsilon=epsilon, shrinkage_n0=shrinkage_n0)
    return float(weights[0])  # weight assigned to the feature-signal column


def lrsi_scores(score_matrix: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """LRSI(c) = 100 * sum_d(w_d * S_d(c)) for every clause (row)."""
    return 100.0 * (score_matrix @ weights)


def classify(lrsi: float, low_medium_cut: float = DEFAULT_LOW_MEDIUM_CUT,
             medium_high_cut: float = DEFAULT_MEDIUM_HIGH_CUT) -> str:
    """3-tier clause classification. `low_medium_cut`/`medium_high_cut`
    default to the fixed cold-start values but are meant to be overridden
    with risk_engine.thresholds.ThresholdRegistry's Jenks-derived cuts once
    enough reference data exists — see hybrid_engine.HybridExplainableRiskEngine."""
    if lrsi >= medium_high_cut:
        return "High"
    if lrsi >= low_medium_cut:
        return "Medium"
    return "Low"


def classify_4tier(score: float, low_medium_cut: float, medium_high_cut: float,
                    high_critical_cut: float) -> str:
    """4-tier document classification (Low/Medium/High/Critical) — same
    inclusive-lower-bound convention as classify(), extended with one more
    cut. Cuts default to risk_engine.thresholds.DEFAULT_DOCUMENT_CUTS at
    the call site until enough reference documents exist for Jenks to
    replace them."""
    if score >= high_critical_cut:
        return "Critical"
    if score >= medium_high_cut:
        return "High"
    if score >= low_medium_cut:
        return "Medium"
    return "Low"


def gini_coefficient(values: np.ndarray) -> float:
    """Standard Gini coefficient of the per-clause LRSI distribution
    (0 = risk spread evenly across clauses, 1 = concentrated in one
    clause). Replaces the old system's fixed '+10 points if >30% of
    clauses are High risk' step function with a continuous, citable
    inequality statistic."""
    if len(values) < 2 or np.sum(values) == 0:
        return 0.0
    sorted_v = np.sort(values)
    n = len(values)
    cum = np.cumsum(sorted_v)
    g = (n + 1 - 2 * np.sum(cum) / cum[-1]) / n
    return float(max(0.0, min(1.0, g)))


def document_risk_score(lrsi_values: np.ndarray, concentration_lambda: float = 0.15) -> float:
    """mean(LRSI) scaled up by a Gini-based concentration term. `lambda` is
    a single, disclosed, ablatable global constant — not a per-phrase
    table — controlling how much a concentration of risk in a few severe
    clauses raises the document score above a plain average."""
    mean_lrsi = float(np.mean(lrsi_values))
    g = gini_coefficient(lrsi_values)
    return min(100.0, mean_lrsi * (1.0 + concentration_lambda * g))
