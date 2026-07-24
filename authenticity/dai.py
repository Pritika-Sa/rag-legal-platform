"""Fusion stage of the Authenticity Verification Engine: combines the 7
factors' scores into one Document Authenticity Index (DAI), 0-100.

Reuses risk_engine.fusion.entropy_weights and risk_engine.thresholds'
Jenks/ThresholdRegistry machinery verbatim — same fusion MATH as the risk
engine — but against a completely separate reference corpus and a
separate ThresholdRegistry instance, per the hard independence constraint
this whole redesign was built under: a document can be High Authenticity/
High Risk or the reverse, and nothing in this module ever reads a risk
field (risk_score, risk_level, dimension_breakdown) — enforced by
construction (this module has no import of anything under risk_engine/
except the two pure-math functions named above), not just by convention.

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
"goodness of variance fit" logic as the risk engine, one level up. With
fewer than 2 usable historical rows (true today — nothing calls this
module from the live pipeline yet, so there is no real reference corpus),
entropy_weights' own existing n<2 fallback applies: equal weights, the
same cold-start behavior already tested for the risk engine.

Factors that report applicable=False for a given document (Factor 2 for
document types outside the mandatory-clause registry, Factor 3/5/6 for
formats/types they don't cover, Factor 4 for non-paginated documents) — or
that simply weren't run at all — contribute no signal for that document:
excluded from that document's fusion entirely, weight redistributed among
the applicable factors, never scored as 0. An inapplicable factor is
"no evidence," not "bad evidence."

classify_4tier's Low/Medium/High/Critical labels are risk-flavored
(Critical = worst) and would read backwards for authenticity (higher DAI =
better, not worse) if reused verbatim, so this module reuses the *cut*
values but supplies its own authenticity-appropriate tier labels.
"""

from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field

from risk_engine.fusion import entropy_weights
from risk_engine.thresholds import DEFAULT_DOCUMENT_CUTS, ThresholdRegistry

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
    authenticity_level: str = Field(description="'Authentic' / 'Likely Authentic' / 'Suspicious' / 'Highly Suspicious' / 'Insufficient Signal'")
    confidence: float = Field(description="0-100, entropy-weighted average of the applicable factors' own confidence")
    weights_data_derived: bool = Field(description="False when weights fell back to equal-weight cold start")
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


def _classify_authenticity(score: float, cuts) -> str:
    low_medium, medium_high, high_critical = cuts
    if score >= high_critical:
        return "Authentic"
    if score >= medium_high:
        return "Likely Authentic"
    if score >= low_medium:
        return "Suspicious"
    return "Highly Suspicious"


def assess_document_authenticity(
    factor_results: Dict[str, Any],
    reference_corpus: Optional[List[Dict[str, float]]] = None,
    threshold_registry: Optional[ThresholdRegistry] = None,
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

    cuts = threshold_registry.document_thresholds().cuts if threshold_registry is not None else DEFAULT_DOCUMENT_CUTS
    level = _classify_authenticity(dai_score, cuts)

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

    return DocumentAuthenticityResult(
        dai_score=dai_score, authenticity_level=level, confidence=overall_confidence,
        weights_data_derived=weights_data_derived, contributions=contributions, evidence=evidence,
    )
