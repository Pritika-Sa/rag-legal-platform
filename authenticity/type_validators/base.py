"""Shared primitives for Factor 8 of the Authenticity Verification Engine:
document-type-specific validators. This is an ADDITIVE factor layered on
top of the existing 7 (see authenticity/__init__.py) — every check here
returns the same flat evidence shape:

    {"passed": bool, "confidence": 0-1, "evidence": str, "reason": str, "applicable": bool}

`applicable=False` means "no evidence available to check this," never a
failure — a check that can't run (e.g. no vehicle identifiers in a life
insurance policy) is excluded from scoring entirely, not treated as
negative evidence. This mirrors the "not applicable, never penalized"
posture already used by every one of the 7 generic factors (structure.py,
clauses.py, cross_field.py, ...).
"""

import json
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_WEIGHTS_PATH = Path(__file__).resolve().parent.parent.parent / "rules" / "document_validator_weights.json"
_DEFAULT_WEIGHT = 1.0

# Same "same real-world thing, worded slightly differently" fuzzy-match
# threshold agents.feature_extraction_agent and authenticity/cross_field.py
# already established, reused rather than inventing a third threshold for
# a structurally identical judgment (OCR-tolerant near-equality).
FUZZY_MATCH_RATIO = 0.5


def _load_weights() -> Dict[str, Dict[str, float]]:
    with _WEIGHTS_PATH.open(encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


_WEIGHTS = _load_weights()


def weights_for(document_type: str) -> Dict[str, float]:
    """Per-check weights for `document_type`, disclosed in
    rules/document_validator_weights.json — see that file's _comment for
    why these are cold-start defaults, not calibrated constants. A check
    with no entry falls back to a neutral weight of 1.0 rather than 0
    (silently zeroing it out would be a much more surprising failure mode
    than just treating it as average-importance)."""
    return _WEIGHTS.get(document_type, {})


class EvidenceCheck(BaseModel):
    name: str
    passed: bool
    confidence: float = Field(ge=0.0, le=1.0, description="0-1: how reliable this specific extraction/check is.")
    evidence: str = Field(description="The concrete fact extracted (or absence noted) — never a generic comment.")
    reason: str = Field(description="Why this check passed/failed, or why it is not applicable.")
    applicable: bool = Field(description="False when there was no relevant evidence to check at all.")


class DocumentValidatorFactorResult(BaseModel):
    """Duck-types the same 4 attributes every other authenticity factor
    exposes (applicable/score/confidence/evidence) so it plugs into
    authenticity/dai.py's generic fusion loop and agents/authenticity_agent.py's
    generic FactorSummary construction with zero changes to either — plus
    the richer, structured fields the document-type-validator layer needs
    for its own explanation output (evidence coverage, applicable/skipped
    check names, warnings, per-check rule breakdown)."""

    applicable: bool
    score: float = Field(ge=0.0, le=1.0, description="Weighted pass-rate across applicable checks only, 0-1.")
    confidence: float = Field(ge=0.0, le=100.0, description="0-100: coverage x mean per-check confidence.")
    document_type: str
    checks: List[EvidenceCheck] = Field(default_factory=list)
    applicable_checks: List[str] = Field(default_factory=list)
    skipped_checks: List[str] = Field(default_factory=list, description="Checks with applicable=False for this document.")
    warnings: List[str] = Field(default_factory=list, description="Reasons for every applicable check that failed.")
    evidence_coverage: float = Field(default=0.0, ge=0.0, le=1.0, description="len(applicable) / len(total checks).")
    evidence: List[str] = Field(default_factory=list, description="Human-readable ✓/✗/⚪ lines, one per check.")


def _not_applicable(document_type: str, reason: str) -> DocumentValidatorFactorResult:
    return DocumentValidatorFactorResult(
        applicable=False, score=0.0, confidence=0.0, document_type=document_type, evidence=[reason],
    )


def fuzzy_majority_fraction(values: List[str]) -> float:
    """Fraction of `values` that fuzzy-match the most common ("mode")
    value — the same OCR-tolerant "how consistent is this repeated field"
    idiom authenticity/cross_field.py uses, reimplemented here (not
    imported from there) so this validator layer stays self-contained and
    independently testable rather than reaching into another factor's
    private helpers."""
    if not values:
        return 0.0
    from collections import Counter

    mode_value, _ = Counter(values).most_common(1)[0]
    matches = sum(1 for v in values if SequenceMatcher(None, v, mode_value).ratio() >= FUZZY_MATCH_RATIO)
    return matches / len(values)


def aggregate_checks(
    document_type: str, checks: List[EvidenceCheck], weights: Dict[str, float],
) -> DocumentValidatorFactorResult:
    """Turns a flat list of EvidenceChecks into the factor-level result.

    Score = Σ(weight_i · confidence_i · passed_i) / Σ(weight_i · confidence_i)
    over APPLICABLE checks only — positive evidence (a passed check) pulls
    the score up in proportion to its weight and confidence; negative
    evidence (a failed-but-applicable check) still counts in the
    denominator, pulling the score down. Not-applicable checks are excluded
    from both the numerator and denominator entirely: "ignored," never
    "penalty," per this engine's core rule that missing evidence is not
    forgery evidence.

    Confidence = evidence_coverage x mean(confidence of applicable checks)
    — deliberately a DIFFERENT formula from score, so the two can diverge
    exactly the way they're supposed to (e.g. 2 of 12 checks applicable and
    both passing scores 100% but low confidence, correctly reading as
    "insufficient evidence" rather than "definitely genuine")."""
    if not checks:
        return _not_applicable(document_type, "No document-type-specific checks were run.")

    applicable = [c for c in checks if c.applicable]
    skipped = [c.name for c in checks if not c.applicable]
    coverage = len(applicable) / len(checks)

    logger.debug(
        f"[type_validators:{document_type}] applicable={ [c.name for c in applicable] } "
        f"skipped={skipped} evidence_coverage={coverage:.2f}"
    )

    if not applicable:
        result = DocumentValidatorFactorResult(
            applicable=True, score=0.0, confidence=0.0, document_type=document_type,
            checks=checks, applicable_checks=[], skipped_checks=skipped, evidence_coverage=0.0,
            evidence=[f"None of the {len(checks)} document-type-specific check(s) for '{document_type}' "
                      f"found any relevant evidence in this document."],
        )
        logger.debug(f"[type_validators:{document_type}] final score=0.0 confidence=0.0 (no applicable evidence)")
        return result

    weighted_denominator = sum(weights.get(c.name, _DEFAULT_WEIGHT) * c.confidence for c in applicable)
    weighted_numerator = sum(
        weights.get(c.name, _DEFAULT_WEIGHT) * c.confidence * (1.0 if c.passed else 0.0) for c in applicable
    )
    score = (weighted_numerator / weighted_denominator) if weighted_denominator > 0 else 0.0
    mean_confidence = sum(c.confidence for c in applicable) / len(applicable)
    confidence = 100.0 * coverage * mean_confidence

    logger.debug(
        f"[type_validators:{document_type}] rule_scores="
        f"{ {c.name: (c.passed, round(c.confidence, 2)) for c in applicable} } "
        f"final_score={score:.4f} confidence={confidence:.2f}"
    )

    warnings = [c.reason for c in applicable if not c.passed]
    evidence_lines = []
    for c in checks:
        if not c.applicable:
            evidence_lines.append(f"⚪ {c.name.replace('_', ' ')}: {c.reason}")
        elif c.passed:
            evidence_lines.append(f"✓ {c.name.replace('_', ' ')}: {c.evidence}")
        else:
            evidence_lines.append(f"✗ {c.name.replace('_', ' ')}: {c.evidence} — {c.reason}")
    evidence_lines.append(
        f"Evidence coverage: {len(applicable)}/{len(checks)} checks applicable "
        f"({sum(1 for c in applicable if c.passed)} passed, "
        f"{sum(1 for c in applicable if not c.passed)} failed)."
    )

    return DocumentValidatorFactorResult(
        applicable=True, score=round(score, 4), confidence=round(confidence, 2), document_type=document_type,
        checks=checks, applicable_checks=[c.name for c in applicable], skipped_checks=skipped,
        warnings=warnings, evidence_coverage=round(coverage, 4), evidence=evidence_lines,
    )
