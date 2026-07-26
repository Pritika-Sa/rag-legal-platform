"""Read-only explainability and multi-label layer for clause-type detection.

Re-derives the same regex/keyword signals agents.rule_engine.detect_clause_type
uses internally and surfaces them per clause, without changing that function's
signature, CLAUSE_RULES content, or any other Rule Engine behavior. Kept in
its own module so agents/rule_engine.py stays untouched.

detect_clause_types_multilabel() is a separate, opt-in capability: a clause
can legitimately be both a Payment clause and a Termination clause (e.g. "if
Client fails to pay within 30 days, Provider may terminate this Agreement"),
so this returns every category that clears the confidence bar instead of only
the single best match. It does not replace agents.rule_engine.detect_clause_type
or agents.clause_identifier_agent.identify_clauses — every existing caller
(clause_identifier_agent, importance_agent, the Authenticity Engine's
`classification` field, Risk Engine labeling, ChromaDB metadata) still gets
exactly one clause_type per clause, unchanged. Multi-label output is additive,
for callers that explicitly want it.
"""

import re
from typing import Any, Dict, List

from agents.clause_identifier_agent import MIN_CONFIDENCE
from agents.rule_engine import CLAUSE_RULES, detect_clause_type, matched_keywords

__all__ = ["explain_clause_detection", "detect_clause_types_multilabel"]


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _score_category(text_lower: str, first_line_lower: str, clause_type: str, rules: dict) -> Dict[str, Any]:
    """Same scoring formula as agents.rule_engine.detect_clause_type's inner
    loop, but returns the full evidence trace for one category instead of
    just a number, so both explain_clause_detection and
    detect_clause_types_multilabel can share one implementation. Keyword
    matching delegates to rule_engine.matched_keywords (Sprint 4B,
    word-boundary-anchored) rather than re-implementing its own substring
    check, so this module can never silently disagree with
    detect_clause_type about what counts as a match."""
    matched_kws = matched_keywords(clause_type, text_lower)
    regex_match = re.search(rules["regex"], text_lower)
    heading_bonus = 0.15 if clause_type.lower() in first_line_lower else 0.0
    score = min(1.0, round(0.25 * bool(regex_match) + 0.10 * min(len(matched_kws), 5) + heading_bonus, 2))

    reason_parts = []
    if regex_match:
        reason_parts.append(f'regex matched "{regex_match.group(0)}"')
    if matched_kws:
        reason_parts.append(f"{len(matched_kws)} keyword(s) matched: {', '.join(matched_kws)}")
    reason = (
        f"Classified as '{clause_type}' because " + "; ".join(reason_parts)
        if reason_parts
        else f"Classified as '{clause_type}' by best-available score."
    )

    return {
        "clause_type": clause_type,
        "confidence": score,
        "matched_keywords": matched_kws,
        "matched_regex": regex_match.group(0) if regex_match else None,
        "regex_pattern": rules["regex"],
        "reason": reason,
    }


def explain_clause_detection(text: str) -> Dict[str, Any]:
    """Returns the clause type detect_clause_type(text) would pick, plus the
    evidence behind it: which keywords hit, the matched regex snippet (if
    any), the full regex pattern for that category, and a human-readable
    reason string."""
    clause_type, confidence = detect_clause_type(text)

    if clause_type not in CLAUSE_RULES:
        return {
            "clause_type": clause_type,
            "confidence": confidence,
            "matched_keywords": [],
            "matched_regex": None,
            "regex_pattern": None,
            "reason": "No clause-type rule scored above the detection threshold.",
        }

    text_lower = text.lower()
    first_line_lower = _first_line(text).lower()
    return _score_category(text_lower, first_line_lower, clause_type, CLAUSE_RULES[clause_type])


def detect_clause_types_multilabel(text: str, min_confidence: float = MIN_CONFIDENCE) -> List[Dict[str, Any]]:
    """Evaluates `text` against every CLAUSE_RULES category — not just the
    single best match — and returns all categories whose score clears
    `min_confidence` (same threshold agents.clause_identifier_agent uses for
    single-label detection), each with its own confidence and explainability
    trace. Sorted by confidence descending. Returns [] if no category clears
    the bar, matching detect_clause_type's own "General" (no match) case."""
    text_lower = text.lower()
    first_line_lower = _first_line(text).lower()

    matches = [
        _score_category(text_lower, first_line_lower, clause_type, rules)
        for clause_type, rules in CLAUSE_RULES.items()
    ]
    matches = [m for m in matches if m["confidence"] >= min_confidence]
    matches.sort(key=lambda m: m["confidence"], reverse=True)
    return matches
