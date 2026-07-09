import re
from difflib import SequenceMatcher
from itertools import combinations
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from agents.rule_engine import extract_dates, extract_durations, extract_money, extract_obligations

TEMPORAL_KEYWORDS = ["effective date", "notice period", "cure period", "term of this agreement", "renewal"]
PAYMENT_KEYWORDS = ["late fee", "interest", "penalty", "due within", "payment terms"]

MAX_CONTRADICTIONS = 15


class ContradictionItem(BaseModel):
    contradiction_type: str = Field(description="Type: Conflicting Clauses, Inconsistent Obligations, Contradictory Dates, Payment Conflicts, or Timeline Conflicts.")
    severity: str = Field(description="Severity: High, Medium, or Low")
    affected_clauses: List[str] = Field(description="List of section names or clause snippets that are in conflict")
    explanation: str = Field(description="Detailed explanation of why these clauses conflict")
    resolution: str = Field(description="Suggested resolution or redrafting advice")


def _enrich(clause: Dict[str, Any]) -> Dict[str, Any]:
    text = clause.get("text_content", "")
    text_lower = text.lower()
    return {
        "section_name": clause.get("section_name", "Clause"),
        "classification": clause.get("classification", "General"),
        "text_lower": text_lower,
        "dates": extract_dates(text),
        "durations": extract_durations(text),
        "money": extract_money(text),
        "obligations": extract_obligations(text),
    }


def find_contradictions(clauses: List[Dict[str, Any]]) -> List[ContradictionItem]:
    """Pairwise, rule-based contradiction detection (Stage 2, no LLM).

    Document clause counts are small (tens, not thousands), so an O(n^2)
    pairwise scan over already-extracted dates/durations/money/obligations
    is cheap and avoids ever sending full clause text to an LLM.
    """
    if len(clauses) < 2:
        return []

    enriched = [_enrich(c) for c in clauses]
    items: List[ContradictionItem] = []
    seen_keys = set()

    def _add(contradiction_type, severity, a_name, b_name, explanation, resolution):
        key = (contradiction_type, frozenset([a_name, b_name]))
        if key in seen_keys:
            return
        seen_keys.add(key)
        items.append(ContradictionItem(
            contradiction_type=contradiction_type, severity=severity,
            affected_clauses=[a_name, b_name], explanation=explanation, resolution=resolution,
        ))

    for a, b in combinations(enriched, 2):
        if a["section_name"] == b["section_name"]:
            continue

        # Contradictory dates / timeline conflicts between clauses that both
        # discuss time-sensitive terms.
        if any(kw in a["text_lower"] for kw in TEMPORAL_KEYWORDS) and any(kw in b["text_lower"] for kw in TEMPORAL_KEYWORDS):
            dates_a, dates_b = set(a["dates"]), set(b["dates"])
            if dates_a and dates_b and not (dates_a & dates_b):
                _add(
                    "Contradictory Dates", "Medium", a["section_name"], b["section_name"],
                    f"'{a['section_name']}' references date(s) {sorted(dates_a)} while "
                    f"'{b['section_name']}' references different date(s) {sorted(dates_b)} "
                    f"for related time-sensitive terms.",
                    "Align the referenced dates or clarify which clause governs.",
                )
            durations_a, durations_b = set(a["durations"]), set(b["durations"])
            if durations_a and durations_b and durations_a != durations_b:
                _add(
                    "Timeline Conflicts", "Medium", a["section_name"], b["section_name"],
                    f"'{a['section_name']}' specifies duration(s) {sorted(durations_a)} while "
                    f"'{b['section_name']}' specifies {sorted(durations_b)} for related obligations.",
                    "Reconcile the durations referenced in both clauses.",
                )

        # Payment conflicts between two Payment-classified clauses citing
        # different figures for similar payment terms.
        if a["classification"] == "Payment" and b["classification"] == "Payment":
            if any(kw in a["text_lower"] for kw in PAYMENT_KEYWORDS) and any(kw in b["text_lower"] for kw in PAYMENT_KEYWORDS):
                money_a, money_b = set(a["money"]), set(b["money"])
                if money_a and money_b and money_a != money_b:
                    _add(
                        "Payment Conflicts", "High", a["section_name"], b["section_name"],
                        f"'{a['section_name']}' cites payment figures {sorted(money_a)} while "
                        f"'{b['section_name']}' cites {sorted(money_b)}, which may conflict.",
                        "Confirm which payment terms are authoritative and remove the conflicting figure.",
                    )

        # Inconsistent obligations: same subject, similar object phrase, but
        # one clause negates the obligation and the other doesn't.
        for s1, r1, t1 in a["obligations"]:
            for s2, r2, t2 in b["obligations"]:
                if s1.lower() != s2.lower():
                    continue
                ratio = SequenceMatcher(None, t1.lower(), t2.lower()).ratio()
                negated_1, negated_2 = "not" in r1.lower(), "not" in r2.lower()
                if ratio > 0.7 and negated_1 != negated_2:
                    _add(
                        "Inconsistent Obligations", "High", a["section_name"], b["section_name"],
                        f"'{a['section_name']}' states '{s1} {r1} {t1}' while '{b['section_name']}' "
                        f"states '{s2} {r2} {t2}', which appear contradictory.",
                        "Clarify which obligation applies and remove the conflicting statement.",
                    )

        # Conflicting governing-law / jurisdiction designations.
        if a["classification"] == "Jurisdiction" and b["classification"] == "Jurisdiction":
            states_a = set(re.findall(r"state of ([a-z ]+)", a["text_lower"]))
            states_b = set(re.findall(r"state of ([a-z ]+)", b["text_lower"]))
            if states_a and states_b and states_a != states_b:
                _add(
                    "Conflicting Clauses", "High", a["section_name"], b["section_name"],
                    f"'{a['section_name']}' designates {sorted(states_a)} as governing jurisdiction "
                    f"while '{b['section_name']}' designates {sorted(states_b)}.",
                    "Consolidate into a single governing law/jurisdiction clause.",
                )

    return items[:MAX_CONTRADICTIONS]
