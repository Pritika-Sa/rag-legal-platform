"""Data-derived classification thresholds — replaces the fixed 35/70
(clause-level Low/Medium/High) and 35/60/80 (document-level
Low/Medium/High/Critical) cut points with breaks computed by Jenks Natural
Breaks Optimization (Fisher, 1958; Jenks, 1967) over the actual
distribution of LRSI scores this installation has produced, instead of two
or three numbers picked by an author.

Jenks partitions a 1-D distribution into k classes by minimizing the sum of
within-class variance (equivalently, maximizing between-class variance) —
the same "goodness of variance fit" criterion the geography/statistics
literature uses for choropleth map class breaks, directly applicable here:
turning a continuous LRSI score into a small number of natural,
data-supported classes is the same problem.

Falls back to the original fixed cut points when there isn't yet enough
reference data to compute stable breaks (MIN_REFERENCE_SIZE) — the same
cold-start philosophy as fusion.entropy_weights' small-n shrinkage: a
principled fixed default beats an unstable data-derived one when the
sample is too small to trust.
"""

import random
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

MIN_REFERENCE_SIZE = 30
MAX_SAMPLE_SIZE = 1500  # Jenks below is O(n^2 * k); caps the *reference sample*, not the corpus itself
                        # (measured ~0.05s at 500 points / 4 classes -> ~0.5s at 1500, fine for a cached, infrequent recompute)

DEFAULT_CLAUSE_CUTS: Tuple[float, float] = (35.0, 70.0)
DEFAULT_DOCUMENT_CUTS: Tuple[float, float, float] = (35.0, 60.0, 80.0)


def jenks_breaks(values: List[float], n_classes: int) -> List[float]:
    """Exact Fisher-Jenks natural breaks via dynamic programming (Fisher,
    1958 — the algorithm behind Jenks' 1967 classification method).
    Returns n_classes+1 boundary values: [min, break_1, ..., break_{k-1}, max].
    Requires len(values) >= n_classes.

    Each interior break is an actual data value — the maximum member of the
    class below it, not a midpoint of the gap between classes. Callers that
    classify with `score >= cut` (as risk_engine.fusion.classify does, and
    as compute_thresholds' cuts are meant to be used) will therefore place a
    future score that exactly equals a break into the class above, one
    class higher than the single historical reference point that defined
    that break — a documented, effectively-zero-probability edge case for
    continuous LRSI scores, not a systematic bias.
    """
    data = sorted(values)
    n = len(data)
    if n < n_classes:
        raise ValueError(f"Need at least {n_classes} values to compute {n_classes} Jenks classes, got {n}")

    # lower_class_limits[l][j]: the data index (1-based) where class j's
    # bottom boundary sits, for the best partition of the first l values
    # into j classes. variance_combinations[l][j]: that partition's total
    # within-class sum-of-squared-deviations.
    lower_class_limits = [[0.0] * (n_classes + 1) for _ in range(n + 1)]
    variance_combinations = [[float("inf")] * (n_classes + 1) for _ in range(n + 1)]

    for i in range(1, n_classes + 1):
        lower_class_limits[1][i] = 1
        variance_combinations[1][i] = 0.0
        for j in range(2, n + 1):
            variance_combinations[j][i] = float("inf")

    variance = 0.0
    for l in range(2, n + 1):
        sum_, sum_squares, w = 0.0, 0.0, 0.0
        for m in range(1, l + 1):
            lower_class_limit = l - m + 1
            val = data[lower_class_limit - 1]
            sum_squares += val * val
            sum_ += val
            w += 1
            variance = sum_squares - (sum_ * sum_) / w
            i4 = lower_class_limit - 1
            if i4 != 0:
                for j in range(2, n_classes + 1):
                    if variance_combinations[l][j] >= (variance + variance_combinations[i4][j - 1]):
                        lower_class_limits[l][j] = lower_class_limit
                        variance_combinations[l][j] = variance + variance_combinations[i4][j - 1]
        lower_class_limits[l][1] = 1
        variance_combinations[l][1] = variance

    k = n
    kclass = [0.0] * (n_classes + 1)
    kclass[n_classes] = data[-1]
    kclass[0] = data[0]
    count_num = n_classes
    while count_num >= 2:
        idx = int(lower_class_limits[k][count_num] - 2)
        kclass[count_num - 1] = data[idx]
        k = int(lower_class_limits[k][count_num] - 1)
        count_num -= 1
    return kclass


def _sample(values: List[float], max_n: int) -> List[float]:
    if len(values) <= max_n:
        return values
    return random.sample(values, max_n)


@dataclass
class ThresholdSet:
    cuts: Tuple[float, ...]
    sample_size: int
    is_data_derived: bool


def compute_thresholds(reference_scores: List[float], n_classes: int,
                        fallback_cuts: Tuple[float, ...]) -> ThresholdSet:
    """Shared computation for both clause-level (n_classes=3) and
    document-level (n_classes=4) thresholds. Falls back to `fallback_cuts`
    below MIN_REFERENCE_SIZE — the pre-Jenks fixed defaults, kept as the
    honest cold-start answer rather than trusting breaks computed from a
    handful of points."""
    clean = [v for v in reference_scores if v is not None]
    if len(clean) < MIN_REFERENCE_SIZE:
        return ThresholdSet(cuts=fallback_cuts, sample_size=len(clean), is_data_derived=False)

    sampled = _sample(clean, MAX_SAMPLE_SIZE)
    breaks = jenks_breaks(sampled, n_classes)
    interior_cuts = tuple(breaks[1:-1])  # drop the sample min/max, keep only the interior class boundaries
    return ThresholdSet(cuts=interior_cuts, sample_size=len(clean), is_data_derived=True)


class ThresholdRegistry:
    """Lazily computes and caches clause-level and document-level
    thresholds from an injected reference-score fetcher — kept DB-agnostic
    on purpose, matching HybridExplainableRiskEngine taking `embed_fn` as
    an injected callable rather than importing an embedding backend
    directly. Computed once per process and reused: Jenks is too expensive
    (and the reference distribution changes too slowly) to recompute on
    every clause scored — call refresh_*() explicitly to recalibrate
    against newer data (e.g. from a periodic maintenance task)."""

    def __init__(
        self,
        fetch_clause_scores: Callable[[], List[float]],
        fetch_document_scores: Callable[[], List[float]],
    ):
        self._fetch_clause_scores = fetch_clause_scores
        self._fetch_document_scores = fetch_document_scores
        self._clause_thresholds: Optional[ThresholdSet] = None
        self._document_thresholds: Optional[ThresholdSet] = None

    def clause_thresholds(self) -> ThresholdSet:
        if self._clause_thresholds is None:
            self.refresh_clause_thresholds()
        return self._clause_thresholds

    def document_thresholds(self) -> ThresholdSet:
        if self._document_thresholds is None:
            self.refresh_document_thresholds()
        return self._document_thresholds

    def refresh_clause_thresholds(self) -> ThresholdSet:
        self._clause_thresholds = compute_thresholds(
            self._fetch_clause_scores(), n_classes=3, fallback_cuts=DEFAULT_CLAUSE_CUTS,
        )
        return self._clause_thresholds

    def refresh_document_thresholds(self) -> ThresholdSet:
        self._document_thresholds = compute_thresholds(
            self._fetch_document_scores(), n_classes=4, fallback_cuts=DEFAULT_DOCUMENT_CUTS,
        )
        return self._document_thresholds
