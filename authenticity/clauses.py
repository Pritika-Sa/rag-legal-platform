"""Factor 2 of the Authenticity Verification Engine: Mandatory Clause
Completeness. Score = importance-tier-weighted fraction of a document
type's conventionally mandatory clause types (drawn from
rules/clause_rules.json's 9 generic commercial-contract categories) that
were actually detected among the document's parsed clauses.

Where Factor 1 (authenticity/structure.py) checks the raw *text* for
section headings, this factor checks the already-computed per-clause
`classification` field (populated by agents.rule_engine.detect_clause_type
during clause_processing_node) — consuming the pipeline's existing output
rather than re-parsing text.

Weighting reuses agents.importance_agent's existing Critical/Important/
Informational base scores (80/55/30) as the per-clause-type weight, rather
than inventing new authenticity-specific numbers: a missing Critical-tier
clause (e.g. Liability) costs more than a missing Informational-tier one
(e.g. Force Majeure), and the weight values themselves are numbers this
codebase already treats as meaningful, not a fresh guess.

Document types whose real mandatory clauses aren't expressible in the 9
generic CLAUSE_RULES categories (e.g. an Insurance Policy's Coverage/
Beneficiary clauses) have no entry in rules/mandatory_clause_rules.json.
For those, this factor reports itself not applicable rather than penalizing
the document against a template that was never going to fit. Unlike Factor
1, there is no generic-minimal fallback to blend toward here — a fixed
"every document needs a Termination clause" template would just reintroduce
the one-size-fits-all problem this redesign exists to remove — so
low-confidence type classifications discount this factor's *confidence*
only, not its required-clause set.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from agents.importance_agent import (
    CRITICAL_BASE_SCORE,
    CRITICAL_TIER_TYPES,
    IMPORTANT_BASE_SCORE,
    IMPORTANT_TIER_TYPES,
    INFORMATIONAL_BASE_SCORE,
)
from services.document_classifier import DocumentTypeClassification
from utils.confidence import evidence_confidence

_RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "mandatory_clause_rules.json"

with _RULES_PATH.open(encoding="utf-8") as f:
    _MANDATORY_CLAUSE_TYPES: Dict[str, List[str]] = json.load(f)


def _tier_weight(clause_type: str) -> int:
    if clause_type in CRITICAL_TIER_TYPES:
        return CRITICAL_BASE_SCORE
    if clause_type in IMPORTANT_TIER_TYPES:
        return IMPORTANT_BASE_SCORE
    return INFORMATIONAL_BASE_SCORE


class ClauseCompletenessFactorResult(BaseModel):
    applicable: bool = Field(description="False if no mandatory-clause template is registered for this document type")
    score: float = Field(description="Tier-weighted fraction of mandatory clause types found, 0-1. 0.0 and not meaningful when applicable=False.")
    confidence: float = Field(description="0-100. 0 when applicable=False.")
    required_types: List[str] = Field(default_factory=list)
    found_types: List[str] = Field(default_factory=list)
    missing_types: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)


def assess_clause_completeness(clauses: List[Dict[str, Any]],
                                classification: DocumentTypeClassification) -> ClauseCompletenessFactorResult:
    required = _MANDATORY_CLAUSE_TYPES.get(classification.document_type)
    if not required:
        return ClauseCompletenessFactorResult(
            applicable=False, score=0.0, confidence=0.0,
            evidence=[
                f"No mandatory-clause template is registered for '{classification.document_type}'; "
                f"this factor does not apply to this document type."
            ],
        )

    present_types = {c.get("classification") for c in clauses}
    found = [t for t in required if t in present_types]
    missing = [t for t in required if t not in present_types]

    found_weight = sum(_tier_weight(t) for t in found)
    total_weight = sum(_tier_weight(t) for t in required)
    score = (found_weight / total_weight) if total_weight else 0.0

    c = classification.confidence
    # Structural evidence (which clause types were actually detected) was
    # gathered regardless of type-classification certainty, so confidence
    # floors at half strength rather than collapsing to zero -- same
    # pattern as authenticity/structure.py.
    confidence = round(100.0 * evidence_confidence(len(found)) * (0.5 + 0.5 * c), 2)

    evidence = [
        f"Applied the '{classification.document_type}' mandatory-clause template "
        f"(type-classification confidence {c:.0%})."
    ]
    evidence += [f"Found: {t}" for t in found] + [f"MISSING: {t}" for t in missing]

    return ClauseCompletenessFactorResult(
        applicable=True, score=round(score, 4), confidence=confidence,
        required_types=required, found_types=found, missing_types=missing, evidence=evidence,
    )
