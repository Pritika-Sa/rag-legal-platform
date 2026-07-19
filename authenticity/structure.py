"""Factor 1 of the Authenticity Verification Engine: Document Structure
Validation. Score = fraction of mandatory sections found for the document's
type — replaces the old agents/authenticity_agent.py's flat per-item
deductions (see the redesign proposal's Problem Statement for why a fixed
-20/-15/-10 per missing item can tank a genuine document over one
unrecognized section).

Consumes Stage 0's output (services.document_classifier.classify_document_type_ranked)
rather than re-classifying the document — classification confidence
directly shapes how strongly the type-specific template is trusted:

  - High confidence: score and evidence come from the type-specific
    template alone.
  - Low confidence: score is a continuous blend of the type-specific and
    generic-minimal templates, weighted by that confidence — never a hard
    switch between one template or the other, so a borderline
    classification doesn't cause a sudden score cliff.
  - No template registered for the detected type (or the type is
    genuinely Unknown Document): falls back to the generic-minimal
    template outright, at a capped confidence — the same graceful-
    degradation posture used throughout this redesign (small-n entropy
    shrinkage, Jenks threshold fallback, Stage 0's own MIN_CONFIDENT_SCORE
    floor).

This module never assigns a manual point value to a missing section — the
detection patterns themselves are the only hand-authored content here,
identical in spirit to rules/clause_rules.json's keyword/regex vocabulary;
the *score* is always a plain fraction.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field

from services.document_classifier import UNKNOWN_DOCUMENT_TYPE, DocumentTypeClassification
from utils.confidence import evidence_confidence

_RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "document_structure_rules.json"
GENERIC_MINIMAL_KEY = "generic_minimal"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _load_compiled_rules() -> Dict[str, List[Tuple[str, List["re.Pattern"]]]]:
    with _RULES_PATH.open(encoding="utf-8") as f:
        raw = json.load(f)
    return {
        doc_type: [
            (section["name"], [re.compile(p, re.IGNORECASE) for p in section["patterns"]])
            for section in entry["sections"]
        ]
        for doc_type, entry in raw.items()
    }


_COMPILED = _load_compiled_rules()
if GENERIC_MINIMAL_KEY not in _COMPILED:
    raise RuntimeError(f"document_structure_rules.json is missing its required '{GENERIC_MINIMAL_KEY}' template")


class StructureFactorResult(BaseModel):
    score: float = Field(description="Fraction of mandatory sections found, 0-1")
    confidence: float = Field(description="0-100")
    template_used: str
    found_sections: List[str] = Field(default_factory=list)
    missing_sections: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)


def _check_template(normalized_text: str, doc_type: str) -> Tuple[List[str], List[str]]:
    found, missing = [], []
    for name, patterns in _COMPILED[doc_type]:
        target = found if any(p.search(normalized_text) for p in patterns) else missing
        target.append(name)
    return found, missing


def _fraction(found: List[str], missing: List[str]) -> float:
    total = len(found) + len(missing)
    return (len(found) / total) if total else 0.0


def assess_structure(full_text: str, classification: DocumentTypeClassification) -> StructureFactorResult:
    normalized = _normalize(full_text or "")
    has_specific_template = (
        classification.document_type != UNKNOWN_DOCUMENT_TYPE
        and classification.document_type in _COMPILED
    )

    if not has_specific_template:
        found, missing = _check_template(normalized, GENERIC_MINIMAL_KEY)
        score = _fraction(found, missing)
        # No type signal to corroborate the template choice at all -- a
        # fixed 0.5 prior (the same "single uncorroborated piece of
        # evidence" reading evidence_confidence(1) would give) times how
        # much of the generic template was actually found.
        confidence = round(100.0 * 0.5 * evidence_confidence(len(found)), 2)
        reason = (
            f"No structure template is registered for '{classification.document_type}'; "
            f"checked the generic minimum (Title/Parties/Date/Signature) instead."
            if classification.document_type != UNKNOWN_DOCUMENT_TYPE
            else "Document type could not be confidently classified; checked the generic minimum instead."
        )
        evidence = [reason]
        evidence += [f"Found: {s}" for s in found] + [f"MISSING: {s}" for s in missing]
        return StructureFactorResult(
            score=round(score, 4), confidence=confidence, template_used=GENERIC_MINIMAL_KEY,
            found_sections=found, missing_sections=missing, evidence=evidence,
        )

    type_found, type_missing = _check_template(normalized, classification.document_type)
    type_score = _fraction(type_found, type_missing)

    c = classification.confidence
    if c >= 1.0:
        score = type_score
    else:
        generic_found, generic_missing = _check_template(normalized, GENERIC_MINIMAL_KEY)
        generic_score = _fraction(generic_found, generic_missing)
        score = c * type_score + (1.0 - c) * generic_score

    # Confidence floors at 50% of the evidence-based figure when the type
    # classification itself was a coin flip (c=0), rising to the full
    # evidence-based figure as c -> 1 -- structural evidence was still
    # gathered even when the type is uncertain, just trusted less.
    confidence = round(100.0 * evidence_confidence(len(type_found)) * (0.5 + 0.5 * c), 2)

    evidence = [f"Applied the '{classification.document_type}' structure template "
                f"(type-classification confidence {c:.0%})."]
    if c < 0.99:
        evidence.append(
            f"Blended {c:.0%} weight on the type-specific template and {1 - c:.0%} on the "
            f"generic minimum, since the document type itself wasn't fully certain."
        )
    evidence += [f"Found: {s}" for s in type_found] + [f"MISSING: {s}" for s in type_missing]

    return StructureFactorResult(
        score=round(score, 4), confidence=confidence, template_used=classification.document_type,
        found_sections=type_found, missing_sections=type_missing, evidence=evidence,
    )
