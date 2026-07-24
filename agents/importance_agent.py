from pydantic import BaseModel, Field
from agents.rule_engine import (
    CRITICAL_TIER_TYPES,
    IMPORTANT_TIER_TYPES,
    detect_clause_type,
    extract_money,
    fired_modifiers,
)

BOILERPLATE_HEADING_WORDS = ["preamble", "notice", "signature", "contact", "recital", "witnesseth"]

UNLIMITED_WORDS = {"uncapped", "unlimited"}
PENALTY_WORDS = {"penalty", "liquidated damages"}

# Base scores per clause-type tier. Named/exported (rather than left as
# inline literals) so other modules can reuse the same "how important does
# this codebase already consider this tier" numbers instead of inventing
# their own — see authenticity/clauses.py, which reuses these as
# mandatory-clause weights rather than hand-picking new authenticity-
# specific weight values.
CRITICAL_BASE_SCORE = 80
IMPORTANT_BASE_SCORE = 55
INFORMATIONAL_BASE_SCORE = 30


class ClauseImportanceResult(BaseModel):
    importance_score: int = Field(description="Importance score between 0 and 100.")
    importance_category: str = Field(description="Importance category: 'Critical', 'Important', or 'Informational'.")
    legal_significance_analysis: str = Field(description="Detailed evaluation of legal significance.")
    financial_impact_analysis: str = Field(description="Detailed evaluation of financial impact.")
    reasoning: str = Field(description="Summary explanation for the final category classification.")


def assess_clause_importance(section_name: str, clause_text: str) -> ClauseImportanceResult:
    """Rule-based clause importance scoring (Stage 2, no LLM).

    Base score comes from the clause's detected type tier, then additive
    modifiers for monetary figures and escalating language (unlimited/
    uncapped exposure, penalty/liquidated-damages terms). Boilerplate
    sections (preambles, notices, signature blocks) are capped low
    regardless of type. Thresholds (75/40) match the categories described
    in the Clause Analysis page UI.
    """
    combined_text = f"{section_name}\n{clause_text}"
    clause_type, _confidence = detect_clause_type(combined_text)

    if clause_type in CRITICAL_TIER_TYPES:
        score = CRITICAL_BASE_SCORE
    elif clause_type in IMPORTANT_TIER_TYPES:
        score = IMPORTANT_BASE_SCORE
    else:
        score = INFORMATIONAL_BASE_SCORE

    escalators, _mitigators = fired_modifiers(combined_text)
    has_money = bool(extract_money(clause_text))
    has_unlimited = any(w in UNLIMITED_WORDS for w in escalators)
    has_penalty = any(w in PENALTY_WORDS for w in escalators)

    reasons = [f"detected clause type '{clause_type}'"]
    if has_money:
        score += 8
        reasons.append("contains monetary figures")
    if has_unlimited:
        score += 12
        reasons.append("uses uncapped/unlimited exposure language")
    if has_penalty:
        score += 10
        reasons.append("references penalties or liquidated damages")

    section_lower = section_name.lower()
    is_boilerplate = clause_type == "General" or any(w in section_lower for w in BOILERPLATE_HEADING_WORDS)
    if is_boilerplate:
        score = min(score, 25)
        reasons.append("heading suggests boilerplate/administrative content, capped low")

    score = max(0, min(100, score))

    if score >= 75:
        category = "Critical"
    elif score >= 40:
        category = "Important"
    else:
        category = "Informational"

    reasoning = f"Scored {score}/100 ({category}): " + "; ".join(reasons) + "."
    legal_significance = (
        f"Clause type '{clause_type}' carries {'high' if score >= 75 else 'moderate' if score >= 40 else 'low'} "
        f"legal significance based on its category and any escalating language present."
    )
    financial_impact = (
        "Monetary figures are present in the clause text." if has_money
        else "No explicit monetary figures were detected in the clause text."
    )

    return ClauseImportanceResult(
        importance_score=score,
        importance_category=category,
        legal_significance_analysis=legal_significance,
        financial_impact_analysis=financial_impact,
        reasoning=reasoning,
    )
