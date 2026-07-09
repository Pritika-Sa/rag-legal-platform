from pydantic import BaseModel, Field
from agents.rule_engine import IMPACT_BASE, detect_clause_type, extract_money, fired_modifiers

REGULATION_WORDS = ["regulation", "statute", "sanction", "fcpa", "compliance"]
BUSINESS_WORDS = ["sla", "deliverable", "milestone", "service level"]
LEGAL_FINANCIAL_ESCALATORS = {"penalty", "liquidated damages", "unlimited", "uncapped"}


class ClauseImpactResult(BaseModel):
    clause: str = Field(description="The name or snippet of the clause being analyzed")
    legal_impact: int = Field(description="Legal Impact score from 0 to 100")
    financial_impact: int = Field(description="Financial Impact score from 0 to 100")
    business_impact: int = Field(description="Business Impact score from 0 to 100")
    compliance_impact: int = Field(description="Compliance Impact score from 0 to 100")


def analyze_clause_impact(section_name: str, clause_text: str) -> ClauseImpactResult:
    """Rule-based four-dimension impact scoring (Stage 2, no LLM). Starts
    from a per-clause-type baseline and nudges each dimension based on
    detected monetary figures, regulatory language, SLA/deliverable
    language, and escalating (penalty/unlimited) terms."""
    combined_text = f"{section_name}\n{clause_text}"
    clause_type, _confidence = detect_clause_type(combined_text)
    legal, financial, business, compliance = IMPACT_BASE.get(clause_type, IMPACT_BASE["General"])

    text_lower = clause_text.lower()
    if extract_money(clause_text):
        financial += 15
    if any(w in text_lower for w in REGULATION_WORDS):
        compliance += 20
    if any(w in text_lower for w in BUSINESS_WORDS):
        business += 20

    escalators, _mitigators = fired_modifiers(clause_text)
    if any(w in LEGAL_FINANCIAL_ESCALATORS for w in escalators):
        legal += 15
        financial += 10

    clamp = lambda v: max(0, min(100, v))
    return ClauseImpactResult(
        clause=section_name,
        legal_impact=clamp(legal),
        financial_impact=clamp(financial),
        business_impact=clamp(business),
        compliance_impact=clamp(compliance),
    )
