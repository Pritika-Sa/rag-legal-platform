"""Factor 3 of the Authenticity Verification Engine: Cross-Field
Consistency. Checks whether the same identifying field — a policy number,
a principal amount, a monthly rent figure — repeats with the *same* value
everywhere it appears in the document. A mismatch (Policy Number
"POL-88213-A" in the header but "POL-99999-Z" in an endorsement clause) is
a strong forgery/tampering signal that neither Factor 1 (are the sections
present) nor Factor 2 (are the clause types present) can catch, since both
only check presence, never cross-location agreement of a single value.

Deliberately narrower than agents/contradiction_agent.py, which compares
*different* clauses' substantive terms against each other (e.g. a $10,000
cap in one clause vs. a $50,000 cap in another) as a legal-quality signal
surfaced on the Contradiction Detection page. This factor instead tracks
one named field's *own* value across every place it recurs, as a
provenance/authenticity signal — the two checks share no code and would
not have flagged each other's target cases.

Only document types with an entry in rules/cross_field_rules.json are
checked; document types without one report not applicable rather than
being scored against fields that don't apply to them (the vehicle-number
example from the original design brief: only checked on document types
where a vehicle number would ever appear). Fields that never repeat in a
given document (appear 0 or 1 times) aren't checkable and are excluded from
the score rather than penalized — nothing was contradicted, there was just
nothing to compare.

Per-field agreement is fuzzy, not byte-exact: a real 8-page scanned
insurance policy restates its Policy Number half a dozen times, and OCR
noise (a dash dropped, a stray character) can make two mentions of the
*same* value normalize to different strings. Requiring exact equality
after normalization treated every one of those OCR slips as forgery
evidence — a real false-positive caught by testing against an actual
scanned document, not a synthetic one. Each occurrence is now scored
against the field's majority ("mode") value, and a field's contribution to
the score is the *fraction* of its occurrences that agree with the
majority, not a binary all-or-nothing verdict.

2026-07-26 audit follow-up: the "agree with the majority" comparator used
to always be the fuzzy character-similarity ratio (SequenceMatcher,
threshold 0.5) agents.feature_extraction_agent established for a
DIFFERENT purpose (matching a dependency-parse subject against a
regex-extracted one). Reused here for value-equality, that same threshold
was too loose to actually catch tampering: '5,00,000' vs '9,00,000' (an
80% different amount) scores 0.833 on that ratio -- comfortably "matching"
despite being a materially different value, confirmed as a real false
positive against a tampered insurance policy during the audit. Fields now
carry a disclosed `kind` in rules/cross_field_rules.json ('money' or 'id');
authenticity/field_matching.py's numeric_match_fraction (parses to a float,
compares the actual value within a small relative tolerance) or
id_match_fraction (Levenshtein edit-distance, tighter than the retired
ratio) is used instead of blanket fuzzy matching wherever a field declares
one. A field with no declared kind keeps the original fuzzy-match behavior
unchanged (kept for anything not yet classified as money/id -- e.g. a
future free-text field where character-similarity really is the right
tool).
"""

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

from pydantic import BaseModel, Field

from agents.feature_extraction_agent import _SUBJECT_AGREEMENT_RATIO
from authenticity.field_matching import id_match_fraction, numeric_match_fraction
from services.document_classifier import DocumentTypeClassification
from utils.confidence import evidence_confidence

_RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "cross_field_rules.json"


class _FieldRule(NamedTuple):
    name: str
    pattern: "re.Pattern"
    kind: Optional[str]  # 'money' | 'id' | None (None = original fuzzy-match behavior)


def _load_compiled_rules() -> Dict[str, List[_FieldRule]]:
    with _RULES_PATH.open(encoding="utf-8") as f:
        raw = json.load(f)
    return {
        doc_type: [
            _FieldRule(field["name"], re.compile(field["pattern"], re.IGNORECASE), field.get("kind"))
            for field in fields
        ]
        for doc_type, fields in raw.items()
        if not doc_type.startswith("_")
    }


_COMPILED = _load_compiled_rules()


def _normalize_value(v: str) -> str:
    return re.sub(r"[,\s]", "", v).strip().upper()


def _fuzzy_match(a: str, b: str) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= _SUBJECT_AGREEMENT_RATIO


def _majority_match_fraction(normalized_values: List[str]) -> float:
    """Fraction of occurrences that fuzzy-match the field's most common
    ("mode") value -- tolerant of OCR noise between two mentions of what
    is really the same value, rather than requiring byte-exact equality.
    Fallback comparator for any field with no declared `kind`."""
    mode_value, _ = Counter(normalized_values).most_common(1)[0]
    matches = sum(1 for v in normalized_values if _fuzzy_match(v, mode_value))
    return matches / len(normalized_values)


def _field_match_fraction(kind: Optional[str], raw_matches: List[str], normalized_values: List[str]) -> float:
    """Dispatches to the field-aware comparator declared by `kind` ('money'
    -> numeric relative-tolerance, 'id' -> edit-distance) per the 2026-07-26
    audit follow-up, falling back to the original fuzzy character-similarity
    comparator for any field with no declared kind, or defensively if a
    'money' field's captured values unexpectedly fail to parse as numbers
    (should not happen for a regex group that only captures digit runs, but
    a parse failure must degrade gracefully, not crash the whole factor)."""
    if kind == "money":
        fraction = numeric_match_fraction(raw_matches)
        if fraction is not None:
            return fraction
    elif kind == "id":
        return id_match_fraction(raw_matches)
    return _majority_match_fraction(normalized_values)


class FieldCheckResult(BaseModel):
    field_name: str
    occurrences: List[str]
    consistent: bool = Field(description="True only if every occurrence fuzzy-matched the majority value")
    match_fraction: float = Field(default=1.0, description="Fraction of occurrences that fuzzy-matched the majority value, 0-1")


class CrossFieldFactorResult(BaseModel):
    applicable: bool = Field(description="False if no cross-field rules are registered for this document type")
    score: float = Field(description="Mean per-field majority-match fraction across checkable fields (2+ occurrences), 0-1")
    confidence: float = Field(description="0-100. 0 when applicable=False or nothing was checkable.")
    checked_fields: List[FieldCheckResult] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)


def assess_cross_field_consistency(full_text: str, classification: DocumentTypeClassification) -> CrossFieldFactorResult:
    fields = _COMPILED.get(classification.document_type)
    if not fields:
        return CrossFieldFactorResult(
            applicable=False, score=0.0, confidence=0.0,
            evidence=[f"No cross-field consistency rules are registered for '{classification.document_type}'."],
        )

    text = full_text or ""
    checked: List[FieldCheckResult] = []
    evidence: List[str] = []
    field_scores: List[float] = []

    for field_rule in fields:
        field_name, pattern, kind = field_rule.name, field_rule.pattern, field_rule.kind
        raw_matches = pattern.findall(text)
        if len(raw_matches) < 2:
            continue
        normalized_values = [_normalize_value(v) for v in raw_matches]
        match_fraction = _field_match_fraction(kind, raw_matches, normalized_values)
        field_scores.append(match_fraction)
        unique_values = sorted(set(normalized_values))
        comparator_note = f" [{kind}-aware comparison]" if kind else ""

        if len(unique_values) == 1:
            evidence.append(f"CONSISTENT: '{field_name}' appears {len(raw_matches)}x with the same value.")
        elif match_fraction >= 1.0:
            evidence.append(
                f"CONSISTENT (minor formatting variation only): '{field_name}' appears {len(raw_matches)}x; "
                f"variants {unique_values} all match within tolerance{comparator_note}."
            )
        else:
            evidence.append(
                f"INCONSISTENT: '{field_name}' appears {len(raw_matches)}x; only {match_fraction:.0%} of "
                f"occurrences agree with each other: {unique_values}{comparator_note}."
            )
        checked.append(FieldCheckResult(
            field_name=field_name, occurrences=raw_matches,
            consistent=match_fraction >= 1.0, match_fraction=round(match_fraction, 4),
        ))

    c = classification.confidence

    if not field_scores:
        return CrossFieldFactorResult(
            applicable=True, score=1.0, confidence=0.0, checked_fields=[],
            evidence=[
                f"None of the {len(fields)} tracked field(s) for '{classification.document_type}' "
                f"repeated enough in this document to check for consistency."
            ],
        )

    score = sum(field_scores) / len(field_scores)
    confidence = round(100.0 * evidence_confidence(len(field_scores)) * (0.5 + 0.5 * c), 2)
    evidence.insert(
        0,
        f"Applied the '{classification.document_type}' cross-field template "
        f"(type-classification confidence {c:.0%}).",
    )

    return CrossFieldFactorResult(
        applicable=True, score=round(score, 4), confidence=confidence,
        checked_fields=checked, evidence=evidence,
    )
