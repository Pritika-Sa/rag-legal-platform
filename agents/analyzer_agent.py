from pydantic import BaseModel, Field
from typing import List
from agents.rule_engine import (
    RISK_TABLE,
    detect_clause_type,
    extract_obligations,
    extract_section_refs,
    risk_score_to_level,
    score_risk_points,
)
from utils.llm_client import invoke_llm_structured


class EntityRelation(BaseModel):
    source: str = Field(description="The source entity or party")
    relation: str = Field(description="The action or link, e.g., 'must pay', 'indemnifies'")
    target: str = Field(description="The target entity, party, or location")


class ClauseAnalysisResult(BaseModel):
    classification: str = Field(description="The clause classification (e.g., Liability, Termination, Confidentiality)")
    risk_category: str = Field(description="The category of risk (e.g., Financial, Compliance, Operational, Legal, None)")
    risk_level: str = Field(description="Severity: High, Medium, Low, or None")
    risk_score: int = Field(default=0, description="Numeric 0-100 risk score derived from phrase-level content, not just clause type")
    explanation: str = Field(description="Why this risk level was assigned and the legal implications")
    entities: List[EntityRelation] = Field(description="Extracted key entities and their relationships")
    dependencies: List[str] = Field(description="Any section names or numbers that this clause references")


def analyze_clause(section_name: str, text_content: str) -> ClauseAnalysisResult:
    """Rule-based clause classification, risk assessment, and structure
    extraction (Stage 2, no LLM). Plain-English simplification is no longer
    produced here — it's only generated on demand via simplification_agent.py.

    Risk is content-based, not just a function of clause type: score_risk_points
    accumulates points for specific phrases actually present in the clause
    (e.g. "without notice", "unlimited liability"), not just a fixed
    per-type baseline.
    """
    combined_text = f"{section_name}\n{text_content}"
    clause_type, _confidence = detect_clause_type(combined_text)
    risk_category, _base_level = RISK_TABLE.get(clause_type, RISK_TABLE["General"])
    risk_score, contributions = score_risk_points(clause_type, text_content)
    risk_level = risk_score_to_level(risk_score)

    explanation = (
        f"Classified as '{clause_type}' ({risk_category} risk category). "
        f"Risk score {risk_score}/100: " + "; ".join(contributions) + "."
    )

    entities = [
        EntityRelation(source=source, relation=relation, target=target)
        for source, relation, target in extract_obligations(text_content)[:5]
    ]
    dependencies = extract_section_refs(text_content)

    return ClauseAnalysisResult(
        classification=clause_type,
        risk_category=risk_category,
        risk_level=risk_level,
        risk_score=risk_score,
        explanation=explanation,
        entities=entities,
        dependencies=dependencies,
    )


class LLMRiskAssessment(BaseModel):
    risk_level: str = Field(description="Severity: High, Medium, Low, or None")
    risk_category: str = Field(description="Category of risk: Financial, Compliance, Operational, Legal, or None")
    risk_score: int = Field(description="Numeric risk score from 0 to 100")
    explanation: str = Field(description="Detailed explanation citing the specific language in the clause that drove this assessment")


def analyze_clause_risk_with_llm(section_name: str, text_content: str) -> LLMRiskAssessment:
    """On-demand LLM risk re-analysis for a single clause — NOT called during
    ingestion. The rule-based score_risk_points() above remains the fast,
    Groq-quota-safe default every clause gets on upload; this exists because
    phrase-matching can miss nuance (implicit obligations, unusual phrasing,
    interactions between sentences) that requires real legal judgment. Only
    invoked when a user explicitly requests it from the UI, one clause at a
    time, so it never reintroduces the N-calls-per-upload latency/quota
    problem the rule-based rewrite was built to avoid."""
    system_instruction = (
        "You are an expert legal counsel and risk analyst. Assess the risk of the "
        "provided contract clause using your full legal judgment — not just keyword "
        "matching. Consider implicit obligations, ambiguous phrasing, and how this "
        "clause could actually play out in a dispute. Assign a risk_category "
        "(Financial, Compliance, Operational, Legal, or None), a risk_level "
        "(High, Medium, Low, or None), and a risk_score (0-100) consistent with that "
        "level. In 'explanation', cite the specific words/phrases in the clause that "
        "drove your assessment."
    )
    prompt = f"Section Heading: {section_name}\nClause Content:\n{text_content}"
    return invoke_llm_structured(system_instruction, prompt, LLMRiskAssessment)
