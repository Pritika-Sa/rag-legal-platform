"""Fusion stage of the Authenticity Verification Engine: combines the 7
factors' scores into one Document Authenticity Index (DAI), 0-100.

Reuses risk_engine.fusion.entropy_weights and risk_engine.thresholds'
compute_thresholds (pure Jenks math) verbatim — same fusion MATH as the
risk engine — but against a completely separate reference corpus and its
own independently-computed cut points, per the hard independence
constraint this whole redesign was built under: a document can be High
Authenticity/High Risk or the reverse, and nothing in this module ever
reads a risk field (risk_score, risk_level, dimension_breakdown) —
enforced by construction (this module has no import of anything under
risk_engine/ except the two pure-math functions named above, never
risk_engine.thresholds.ThresholdRegistry itself, whose cached instance and
document-level cuts belong to risk scoring alone), not just by convention.

Where the risk engine's entropy weights vary dimension importance by how
much each dimension's score varies *across a document's own clauses*,
DAI's entropy weights vary factor importance by how much each factor's
score varies *across this installation's own document history* — the
matrix rows here are past documents, not clauses within one document,
since each factor produces exactly one score per document, not one per
clause. A factor that always scores ~1.0 for every real document (little
discriminative power for telling authentic from suspicious documents
apart) is automatically down-weighted; a factor whose score actually
varies across the document population earns more influence — same
"goodness of variance fit" logic as the risk engine, one level up. Wired
to a real reference corpus (agents.authenticity_agent now passes
database.crud.get_recent_document_authenticity_factor_scores()) as of
2026-07-26 — until an installation has 2+ usable historical rows,
entropy_weights' own existing n<2 fallback applies: equal weights, the
same cold-start behavior already tested for the risk engine.

Factors that report applicable=False for a given document (Factor 2 for
document types outside the mandatory-clause registry, Factor 3/5/6 for
formats/types they don't cover, Factor 4 for non-paginated documents) — or
that simply weren't run at all — contribute no signal for that document:
excluded from that document's fusion entirely, weight redistributed among
the applicable factors, never scored as 0. An inapplicable factor is
"no evidence," not "bad evidence."

Tier classification (2026-07-26 calibration pass): reuses
compute_thresholds' Jenks machinery directly rather than going through
risk_engine.thresholds.ThresholdRegistry.document_thresholds() — that
method is hardcoded to risk's own n_classes=4 and DEFAULT_DOCUMENT_CUTS,
neither of which is the right shape for authenticity's 6-tier calibration
(95/90/80/65/40, matching institutional expectations for how authenticity
scores should read: a document doesn't need to be "the same as risk's
High/Critical split" to be classified). DEFAULT_DAI_CUTS below is DAI's
own disclosed cold-start fallback, used until an installation has 30+
scored documents (compute_thresholds.MIN_REFERENCE_SIZE) to compute
data-derived Jenks breaks from, at which point real cuts replace it —
same cold-start-then-calibrate posture as everywhere else in this engine.
"""

from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field

from risk_engine.fusion import entropy_weights
from risk_engine.thresholds import MIN_REFERENCE_SIZE, compute_thresholds

# 6-tier calibration: interior cuts at 40/65/80/90/95, matching the
# institutional-standard reading of an authenticity score (0-39 Likely
# Manipulated or Forged, 40-64 Suspicious, 65-79 Mostly Authentic, 80-89
# Likely Authentic, 90-94 Strongly Authentic, 95-100 Highly Authentic).
# A disclosed, ablatable cold-start default — same status as risk_engine.
# thresholds.DEFAULT_DOCUMENT_CUTS — not a claim that these exact numbers
# are the only defensible choice, just the honest fallback below
# MIN_REFERENCE_SIZE usable historical scores.
DEFAULT_DAI_CUTS: tuple = (40.0, 65.0, 80.0, 90.0, 95.0)
DAI_TIER_LABELS: tuple = (
    "Likely Manipulated or Forged",
    "Suspicious",
    "Mostly Authentic",
    "Likely Authentic",
    "Strongly Authentic",
    "Highly Authentic",
)

FACTOR_NAMES: List[str] = [
    "structure",
    "clause_completeness",
    "cross_field",
    "entity_verification",
    "digital_verification",
    "metadata_validation",
    "semantic_consistency",
    # Factor 8 (additive, not part of the original 7): document-type-specific
    # validators (authenticity/type_validators/) — applicable=False for any
    # document type without a registered validator, so this never penalizes
    # a document the same way the other 7 factors' own "not applicable"
    # cases don't.
    "document_type_validator",
]


class FactorContribution(BaseModel):
    name: str
    score: float
    confidence: float
    weight: float


class DocumentAuthenticityResult(BaseModel):
    dai_score: float = Field(description="0-100. Higher = more authentic-looking.")
    authenticity_level: str = Field(description=f"One of {DAI_TIER_LABELS + ('Insufficient Signal',)}")
    confidence: float = Field(description="0-100, entropy-weighted average of the applicable factors' own confidence")
    weights_data_derived: bool = Field(description="False when weights fell back to equal-weight cold start")
    tier_cuts_data_derived: bool = Field(default=False, description="False when tier cuts fell back to the fixed cold-start calibration (DEFAULT_DAI_CUTS)")
    contributions: List[FactorContribution] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)


def _select_reference_matrix(reference_corpus: List[Dict[str, float]], factor_names: List[str]) -> np.ndarray:
    """Historical rows are only usable if every currently-applicable factor
    was also applicable (present) for that past document — comparing
    entropy across mismatched factor sets would be meaningless."""
    rows = [
        [doc_scores[name] for name in factor_names]
        for doc_scores in reference_corpus
        if all(doc_scores.get(name) is not None for name in factor_names)
    ]
    return np.array(rows, dtype=float) if rows else np.zeros((0, len(factor_names)))


def _classify_authenticity(score: float, cuts: tuple) -> str:
    """cuts is 5 interior boundaries (low->high); DAI_TIER_LABELS is the
    matching 6 labels (low->high) -- walks from the top down so a score
    sitting exactly on a boundary lands in the higher tier, same
    `score >= cut` convention risk_engine.fusion.classify_4tier uses."""
    for cut, label in zip(reversed(cuts), reversed(DAI_TIER_LABELS[1:])):
        if score >= cut:
            return label
    return DAI_TIER_LABELS[0]


def assess_document_authenticity(
    factor_results: Dict[str, Any],
    reference_corpus: Optional[List[Dict[str, float]]] = None,
    reference_authenticity_scores: Optional[List[float]] = None,
) -> DocumentAuthenticityResult:
    applicable_names = [
        name for name in FACTOR_NAMES
        if factor_results.get(name) is not None and factor_results[name].applicable
    ]

    if not applicable_names:
        return DocumentAuthenticityResult(
            dai_score=0.0, authenticity_level="Insufficient Signal", confidence=0.0,
            weights_data_derived=False,
            evidence=["No authenticity factor produced an applicable result for this document."],
        )

    reference_matrix = _select_reference_matrix(reference_corpus or [], applicable_names)
    weights_data_derived = reference_matrix.shape[0] >= 2
    weights = entropy_weights(reference_matrix) if weights_data_derived else np.full(
        len(applicable_names), 1.0 / len(applicable_names)
    )

    scores = np.array([factor_results[name].score for name in applicable_names])
    confidences = np.array([factor_results[name].confidence for name in applicable_names])

    dai_score = round(float(100.0 * np.dot(weights, scores)), 2)
    overall_confidence = round(float(np.dot(weights, confidences)), 2)

    tier_thresholds = compute_thresholds(
        reference_authenticity_scores or [], n_classes=6, fallback_cuts=DEFAULT_DAI_CUTS,
    )
    level = _classify_authenticity(dai_score, tier_thresholds.cuts)

    contributions = [
        FactorContribution(
            name=name, score=round(float(factor_results[name].score), 4),
            confidence=factor_results[name].confidence, weight=round(float(w), 4),
        )
        for name, w in zip(applicable_names, weights)
    ]

    skipped = [
        name for name in FACTOR_NAMES
        if factor_results.get(name) is not None and not factor_results[name].applicable
    ]
    evidence = [f"Combined {len(applicable_names)} applicable factor(s): {applicable_names}."]
    if skipped:
        evidence.append(f"Skipped {len(skipped)} not-applicable factor(s) for this document: {skipped}.")
    evidence.append(
        "Factor weights were derived from this installation's own document history."
        if weights_data_derived else
        "Factor weights used the equal-weight cold-start default (fewer than 2 comparable historical documents)."
    )
    evidence.append(
        f"Authenticity tier boundaries were derived from {tier_thresholds.sample_size} prior scored "
        f"document(s) in this installation's own history."
        if tier_thresholds.is_data_derived else
        f"Authenticity tier boundaries used the fixed cold-start calibration "
        f"(fewer than {MIN_REFERENCE_SIZE} comparable historical documents)."
    )

    return DocumentAuthenticityResult(
        dai_score=dai_score, authenticity_level=level, confidence=overall_confidence,
        weights_data_derived=weights_data_derived, tier_cuts_data_derived=tier_thresholds.is_data_derived,
        contributions=contributions, evidence=evidence,
    )
