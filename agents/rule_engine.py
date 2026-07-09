"""Shared deterministic core for Stage-2 rule-based agents.

Every agent that used to call an LLM to classify, score, or extract
structure from clause text now goes through the primitives in this file
instead. Keeping them in one place means an examiner (or future maintainer)
only has to review this module to understand the entire non-LLM reasoning
layer of the pipeline.

All rule *content* (keyword lists, regexes, risk tables, phrase-point
tables) lives in JSON files under `rules/` at the repo root, loaded once at
import time. Editing a rule means editing JSON, not Python — no redeploy of
logic needed to retune a threshold or add a keyword.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

_RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


class RuleLoadError(RuntimeError):
    """Raised when a rules/*.json file is missing or malformed. This fails
    loudly at import time (i.e. at Streamlit app startup) by design — a
    legal-risk tool silently running with empty/default rules is worse than
    one that refuses to start until the rule files are fixed."""


def _load_json(filename: str) -> dict:
    path = _RULES_DIR / filename
    if not path.is_file():
        raise RuleLoadError(f"Required rule file not found: {path}")
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise RuleLoadError(f"Malformed JSON in {path}: {e}") from e


def _require(data: dict, key: str, filename: str):
    if key not in data or not data[key]:
        raise RuleLoadError(f"{filename} is missing required, non-empty key '{key}'")
    return data[key]


# ── Clause type rules (regex + keyword vocabularies) ────────────────────────

CLAUSE_RULES: Dict[str, dict] = _load_json("clause_rules.json")
if not CLAUSE_RULES:
    raise RuleLoadError("clause_rules.json loaded but is empty")

# ── Risk rules: levels, per-type base tier, tier->points, phrase->points ───

_risk_raw = _load_json("risk_rules.json")
RISK_LEVELS: List[str] = _require(_risk_raw, "risk_levels", "risk_rules.json")
_risk_table_raw = _require(_risk_raw, "risk_table", "risk_rules.json")
RISK_TABLE: Dict[str, Tuple[str, str]] = {
    ct: (v["category"], v["base_level"]) for ct, v in _risk_table_raw.items()
}
TIER_BASE_POINTS: Dict[str, int] = _require(_risk_raw, "tier_base_points", "risk_rules.json")
RISK_PHRASE_POINTS: Dict[str, Dict[str, int]] = _risk_raw.get("risk_phrase_points", {})

# ── Importance tiers ─────────────────────────────────────────────────────────

_importance_raw = _load_json("importance_rules.json")
CRITICAL_TIER_TYPES = set(_require(_importance_raw, "critical_tier_types", "importance_rules.json"))
IMPORTANT_TIER_TYPES = set(_require(_importance_raw, "important_tier_types", "importance_rules.json"))

# ── Impact baselines ─────────────────────────────────────────────────────────

_impact_raw = _load_json("impact_rules.json")
_impact_base_raw = _require(_impact_raw, "impact_base", "impact_rules.json")
IMPACT_BASE: Dict[str, Tuple[int, int, int, int]] = {
    ct: (v["legal"], v["financial"], v["business"], v["compliance"])
    for ct, v in _impact_base_raw.items()
}

# ── Static clause-type dependency relationships ─────────────────────────────

_dependency_raw = _load_json("dependency_rules.json")
DEPENDENCY_RULES: List[Tuple[str, str, str]] = [
    (d["source"], d["target"], d["relation"])
    for d in _require(_dependency_raw, "dependencies", "dependency_rules.json")
]

# ── Escalation / mitigation phrase weights (point-valued) ───────────────────

_escalation_raw = _load_json("escalation_rules.json")
_mitigation_raw = _load_json("mitigation_rules.json")
ESCALATOR_WEIGHTS: Dict[str, int] = {
    m["phrase"]: m["weight"] for m in _require(_escalation_raw, "modifiers", "escalation_rules.json")
}
MITIGATOR_WEIGHTS: Dict[str, int] = {
    m["phrase"]: m["weight"] for m in _require(_mitigation_raw, "modifiers", "mitigation_rules.json")
}
# Kept as plain lists too, for any caller doing simple membership checks.
MODIFIER_ESCALATORS: List[str] = list(ESCALATOR_WEIGHTS.keys())
MODIFIER_MITIGATORS: List[str] = list(MITIGATOR_WEIGHTS.keys())

# ── Extraction regexes ──────────────────────────────────────────────────────

_MONEY_RE = re.compile(
    r"(?:USD|US\$|\$|₹|INR|Rs\.?|€|£)\s?[\d,]+(?:\.\d+)?(?:\s?(?:million|billion|thousand|lakh|crore))?"
    r"|\b\d+(?:\.\d+)?\s?%",
    re.IGNORECASE,
)

_DATE_RE = re.compile(
    r"\b(?:\d{1,2}(?:st|nd|rd|th)?\s+day\s+of\s+)?"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    re.IGNORECASE,
)

_DURATION_RE = re.compile(r"\b(\d+)\s?(day|days|month|months|year|years|week|weeks)\b", re.IGNORECASE)

_SECTION_REF_RE = re.compile(r"\b(?:Section|Clause|Article|Paragraph)\s+\d+(?:\.\d+)*", re.IGNORECASE)

_OBLIGATION_RE = re.compile(
    r"\b([A-Z][A-Za-z&,.]{2,40})\s+(shall(?:\s+not)?|must(?:\s+not)?|will(?:\s+not)?|agrees to)\s+([^.\n]{3,80})"
)


def extract_money(text: str) -> List[str]:
    return _MONEY_RE.findall(text)


def extract_dates(text: str) -> List[str]:
    return _DATE_RE.findall(text)


def extract_durations(text: str) -> List[Tuple[int, str]]:
    return [(int(n), unit.lower()) for n, unit in _DURATION_RE.findall(text)]


def extract_section_refs(text: str) -> List[str]:
    seen = []
    for match in _SECTION_REF_RE.findall(text):
        if match not in seen:
            seen.append(match)
    return seen


def extract_obligations(text: str) -> List[Tuple[str, str, str]]:
    """Returns (source, relation, target) triples for 'X shall/must/will Y' phrasing."""
    return [(m[0].strip(), m[1].strip(), m[2].strip()) for m in _OBLIGATION_RE.findall(text)]


# ── Clause type detection (replaces per-block LLM verification) ────────────

def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def detect_clause_type(text: str) -> Tuple[str, float]:
    """Scores `text` against every CLAUSE_RULES entry and returns the
    best-matching (clause_type, confidence in [0,1]). Confidence combines a
    regex hit, keyword density (capped so density can't dominate), and a
    small bonus if the clause type name appears in the block's heading line."""
    text_lower = text.lower()
    first_line_lower = _first_line(text).lower()

    best_type = "General"
    best_score = 0.0
    for c_type, rules in CLAUSE_RULES.items():
        keyword_hits = sum(1 for kw in rules["keywords"] if kw in text_lower)
        regex_hit = bool(re.search(rules["regex"], text_lower))
        heading_bonus = 0.15 if c_type.lower() in first_line_lower else 0.0
        score = min(1.0, round(0.25 * regex_hit + 0.10 * min(keyword_hits, 5) + heading_bonus, 2))
        if score > best_score:
            best_score = score
            best_type = c_type

    return best_type, best_score


# ── Risk level escalation (ordinal, legacy-compatible) ──────────────────────

def apply_risk_modifiers(base_level: str, text: str) -> str:
    """Shifts `base_level` up/down the RISK_LEVELS ladder based on the total
    escalating/mitigating point weight of language found in `text` (e.g.
    'uncapped' pushes risk up, 'capped at' pulls it back down). Point totals
    are converted into ordinal steps, capped at +3/-2 tiers, so a clause
    packed with escalating language can't jump past 'High' in one shot."""
    text_lower = text.lower()
    escalation_points = sum(w for phrase, w in ESCALATOR_WEIGHTS.items() if phrase in text_lower)
    mitigation_points = sum(w for phrase, w in MITIGATOR_WEIGHTS.items() if phrase in text_lower)
    escalation_steps = min(escalation_points // 15, 3)
    mitigation_steps = min(mitigation_points // 15, 2)
    net_shift = escalation_steps - mitigation_steps

    idx = RISK_LEVELS.index(base_level) if base_level in RISK_LEVELS else 0
    idx = max(0, min(len(RISK_LEVELS) - 1, idx + net_shift))
    return RISK_LEVELS[idx]


def fired_modifiers(text: str) -> Tuple[List[str], List[str]]:
    """Returns (escalators_found, mitigators_found) — used to build
    human-readable 'reasoning' strings instead of an LLM-generated one."""
    text_lower = text.lower()
    escalators = [w for w in MODIFIER_ESCALATORS if w in text_lower]
    mitigators = [w for w in MODIFIER_MITIGATORS if w in text_lower]
    return escalators, mitigators


# ── Content-based numeric risk scoring (Stage 2, no LLM) ────────────────────

def score_risk_points(clause_type: str, text: str) -> Tuple[int, List[str]]:
    """Numeric 0-100 risk score for a clause, built from a base tier score
    plus additive/subtractive points for specific phrases actually present
    in the clause text — unlike apply_risk_modifiers (which only shifts an
    ordinal tier by counting how many generic escalator/mitigator words
    appear), this weights *which* phrase fired and by how much, per clause
    type. Returns (score, contributions) where contributions is a list of
    human-readable strings explaining every point added/subtracted, so
    callers can build an explainable 'why' string instead of a bare number.
    """
    text_lower = text.lower()
    _, base_level = RISK_TABLE.get(clause_type, RISK_TABLE["General"])
    score = TIER_BASE_POINTS.get(base_level, 5)
    contributions = [f"base tier '{base_level}' = {score}"]

    phrase_table = RISK_PHRASE_POINTS.get(clause_type)
    if phrase_table:
        for phrase, points in phrase_table.items():
            if phrase in text_lower:
                score += points
                contributions.append(f"'{phrase}' {'+' if points >= 0 else ''}{points}")
    else:
        # No clause-type-specific table: fall back to the global
        # escalator/mitigator vocabulary as generic point contributions.
        for phrase, points in ESCALATOR_WEIGHTS.items():
            if phrase in text_lower:
                score += points
                contributions.append(f"'{phrase}' +{points}")
        for phrase, points in MITIGATOR_WEIGHTS.items():
            if phrase in text_lower:
                score -= points
                contributions.append(f"'{phrase}' -{points}")

    score = max(0, min(100, score))
    return score, contributions


def detect_query_intent(query: str) -> Dict[str, Any]:
    """Lightweight keyword-only match against CLAUSE_RULES' keyword lists
    (not the regex/confidence scoring meant for whole clause blocks — a
    short question needs simpler matching than a full clause). Returns a
    Chroma-ready metadata filter fragment: {} if no clause-type keyword is
    found (caller must treat this as "no filter", not zero results),
    {"clause_type": "X"} for a single match, or
    {"clause_type": {"$in": [...]}} if the query mentions multiple clause
    types (Chroma accepts this natively as a filter leaf)."""
    query_lower = query.lower()
    matched_types = [
        c_type for c_type, rules in CLAUSE_RULES.items()
        if any(kw in query_lower for kw in rules["keywords"])
    ]
    if not matched_types:
        return {}
    if len(matched_types) == 1:
        return {"clause_type": matched_types[0]}
    return {"clause_type": {"$in": matched_types}}


def risk_score_to_level(score: int) -> str:
    """Maps a numeric 0-100 risk score back to the ordinal risk_level string
    every existing consumer (UI color-coding, contradiction_agent, Chroma
    metadata) expects."""
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    if score >= 15:
        return "Low"
    return "None"
