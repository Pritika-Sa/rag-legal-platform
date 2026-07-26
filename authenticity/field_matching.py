"""Field-aware value-consistency comparison for the Authenticity
Verification Engine (Priority 2 of the 2026-07-26 production audit
follow-up).

Audit finding: agents.feature_extraction_agent._SUBJECT_AGREEMENT_RATIO
(0.5), reused throughout authenticity/cross_field.py, authenticity/
entities.py, and authenticity/type_validators/base.py as a generic "same
value, OCR-tolerant" threshold, is a character-similarity ratio -- for
short numeric/ID strings that ratio is dominated by shared length and
structure, not actual value difference: '500000' vs '900000' (an 80%
different amount) scores 0.833 on SequenceMatcher.ratio(), comfortably
above 0.5, and was reported as "consistent." Confirmed as a real,
reproducible false positive against a tampered insurance policy (an
inflated Sum Assured and an altered Policy Number both passed as
"consistent (minor formatting variation only)").

This module provides two deterministic, field-aware comparators for the
field kinds the audit specifically named -- numeric values, monetary
values, percentages, IDs, document numbers:

  - numeric_match_fraction: parses each occurrence to a float (stripping
    currency symbols, %, commas, and whitespace -- pure formatting, never
    the value) and compares against the field's own most common (mode)
    parsed value within a disclosed relative tolerance. Appropriate for
    money/percentage/plain-numeric fields, where the actual parsed VALUE is
    what matters, not how similar the two strings "look" as text.
  - id_match_fraction: Levenshtein edit-distance based, appropriate for
    opaque alphanumeric identifiers (policy numbers, invoice numbers) that
    have no numeric "value" to compare. Tighter than the retired 0.5 ratio
    threshold -- catches multi-character differences (e.g. 'ABC CORP' vs
    'XYZ CORP') that used to slip through -- but a single-character edit is
    inherently indistinguishable from a single-character OCR misread by
    edit distance alone; MAX_ID_EDIT_DISTANCE stays small and disclosed (1)
    rather than pretending this ambiguity can be fully resolved without a
    second, independent source of truth.

Names/entities (e.g. authenticity/entities.py's party-name consistency,
authenticity/type_validators/insurance_policy.py's customer-name check) are
deliberately OUT OF SCOPE -- the audit's Priority 2 explicitly named
numeric/money/percentage/ID/document-number fields, not names, and
character-fuzzy matching is the right tool for genuine name-form variation
("ABC Corp" vs "ABC Corporation"). Those call sites are unchanged.
"""

import re
from collections import Counter
from typing import List, Optional

# Relative tolerance for numeric/money/percentage fields -- same order of
# magnitude and the same disclosed-constant posture as
# authenticity/type_validators/insurance_policy.py's GST_ARITHMETIC_TOLERANCE
# (0.03), which already established that a few percent of slack absorbs
# realistic rounding/formatting noise without hiding a materially different
# value. Not tuned against any specific sample document.
NUMERIC_RELATIVE_TOLERANCE = 0.03

# Maximum Levenshtein edit distance still treated as "the same identifier,
# OCR noise" for opaque alphanumeric IDs. A disclosed, deliberately small
# constant: edit distance cannot distinguish a genuine one-character OCR
# misread from a genuine one-character forgery (they are literally the same
# edit), so this does not claim to solve that ambiguity; it only stops
# MULTI-character differences (a materially different value) from being
# waved through the way the old 0.5 character-similarity ratio did.
MAX_ID_EDIT_DISTANCE = 1

# Currency/unit tokens stripped BEFORE the digit-only pass below -- must run
# first, since an abbreviation like "Rs." carries its own period that would
# otherwise survive into the digit/dot pass and produce an invalid
# multi-dot string (e.g. "Rs. 5,00,000.00" -> ".5000000.00" if stripped in
# the wrong order).
_CURRENCY_TOKEN_RE = re.compile(r"(?i)\b(?:rs|inr|usd|eur|gbp)\b\.?|[₹$€£%]")
_NUMERIC_STRIP_RE = re.compile(r"[^\d.]")


def parse_numeric(value: str) -> Optional[float]:
    """Strips currency symbols/abbreviations, %, commas, and whitespace --
    pure formatting -- and parses what remains as a float. Returns None
    (not 0) when the value doesn't parse as a plain number, so callers fall
    back to a different comparator rather than silently miscomparing."""
    if not value:
        return None
    cleaned = _CURRENCY_TOKEN_RE.sub("", value)
    cleaned = _NUMERIC_STRIP_RE.sub("", cleaned)
    if not cleaned or cleaned == ".":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _levenshtein(a: str, b: str) -> int:
    """Standard O(len(a)*len(b)) edit-distance DP -- deterministic, no
    external dependency and no ML, same "plain algorithm" posture as
    risk_engine.thresholds.jenks_breaks."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous_row = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current_row = [i]
        for cb in b:
            insert_cost = current_row[-1] + 1
            delete_cost = previous_row[len(current_row)] + 1
            substitute_cost = previous_row[len(current_row) - 1] + (0 if ca == cb else 1)
            current_row.append(min(insert_cost, delete_cost, substitute_cost))
        previous_row = current_row
    return previous_row[-1]


def numeric_match_fraction(
    values: List[str], relative_tolerance: float = NUMERIC_RELATIVE_TOLERANCE,
) -> Optional[float]:
    """Fraction of `values` whose parsed numeric value is within
    `relative_tolerance` of the field's own most common (mode) parsed
    value. Returns None (not a score) if any value fails to parse as a
    plain number -- callers should fall back to a different comparator
    rather than treat a parse failure as a mismatch."""
    parsed = [parse_numeric(v) for v in values]
    if any(p is None for p in parsed):
        return None
    mode_value, _ = Counter(parsed).most_common(1)[0]
    if mode_value == 0:
        return sum(1 for p in parsed if p == 0) / len(parsed)
    matches = sum(1 for p in parsed if abs(p - mode_value) / abs(mode_value) <= relative_tolerance)
    return matches / len(parsed)


def id_match_fraction(values: List[str], max_edit_distance: int = MAX_ID_EDIT_DISTANCE) -> float:
    """Fraction of `values` within `max_edit_distance` edits of the field's
    own most common (mode) value, after whitespace/dash normalization
    (formatting only -- never a value character)."""
    normalized = [re.sub(r"[\s\-]", "", v).upper() for v in values]
    mode_value, _ = Counter(normalized).most_common(1)[0]
    matches = sum(1 for v in normalized if _levenshtein(v, mode_value) <= max_edit_distance)
    return matches / len(normalized)
