import logging
from pydantic import BaseModel, Field
from typing import List, Dict, Any

from services.prompt_builder import build_clause_prompt
from utils.llm_client import invoke_llm_text

logger = logging.getLogger(__name__)

RISK_POINTS = {"High": 90, "Medium": 55, "Low": 25, "None": 5}

RECOMMENDATION_TABLE = {
    "Liability": "Negotiate a liability cap and carve out indirect/consequential damages.",
    "Indemnity": "Narrow the indemnification scope and add a mutual indemnity provision if one-sided.",
    "Termination": "Add a cure period and require written notice before termination takes effect.",
    "Payment": "Clarify payment timelines, late-fee interest rates, and dispute procedures.",
    "Confidentiality": "Confirm confidentiality survives termination and define a reasonable duration.",
    "Compliance": "Verify the compliance obligations map to your actual regulatory footprint.",
    "Jurisdiction": "Confirm the governing law/venue is acceptable and not unduly burdensome.",
    "Force Majeure": "Ensure force majeure events are clearly enumerated and notice periods are workable.",
    "Arbitration": "Confirm arbitration rules/seat are balanced and not overly costly for either party.",
}


class DocumentRiskScoreResult(BaseModel):
    risk_score: int = Field(description="Overall risk score from 0 to 100.")
    risk_level: str = Field(description="Risk level: 'Low', 'Medium', 'High', or 'Critical'.")
    affected_clauses: List[str] = Field(description="List of clause headings that primarily contributed to the risk score.")
    reasoning: str = Field(description="Detailed explanation of why this risk score was assigned.")
    recommendations: str = Field(description="Actionable recommendations to mitigate the identified risks.")


def _aggregate(document_name: str, scored: List[tuple], method_note: str) -> DocumentRiskScoreResult:
    """Shared aggregation math for both the rule-based and LLM-based paths:
    weighted average of per-clause points + a concentration bonus if a large
    share of clauses are High risk, mapped to a 4-tier document risk_level."""
    total = len(scored)
    avg_points = sum(points for _, _, _, points in scored) / total
    high_count = sum(1 for _, _, level, _ in scored if level == "High")
    high_ratio = high_count / total

    concentration_bonus = 10 if high_ratio > 0.3 else 0
    risk_score = max(0, min(100, round(avg_points + concentration_bonus)))

    if risk_score >= 80:
        risk_level = "Critical"
    elif risk_score >= 60:
        risk_level = "High"
    elif risk_score >= 35:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    top_contributors = sorted(scored, key=lambda s: s[3], reverse=True)[:5]
    affected_clauses = [section for section, _, level, _ in top_contributors if level in ("High", "Medium")]

    reasoning = (
        f"{document_name}: {total} clauses assessed, {high_count} at High risk "
        f"({round(high_ratio * 100)}%). Aggregate score {risk_score}/100 derived from a "
        f"weighted average of per-clause risk scores ({method_note})"
        + (" with a concentration bonus applied due to a high share of High-risk clauses." if concentration_bonus else ".")
    )

    recommended_types = {classification for _, classification, level, _ in top_contributors if level in ("High", "Medium")}
    recommendations = " ".join(
        RECOMMENDATION_TABLE[t] for t in recommended_types if t in RECOMMENDATION_TABLE
    ) or "No specific high-risk clause types identified; review the document for general legal soundness."

    return DocumentRiskScoreResult(
        risk_score=risk_score,
        risk_level=risk_level,
        affected_clauses=affected_clauses,
        reasoning=reasoning,
        recommendations=recommendations,
    )


def assess_document_risk(document_name: str, clauses_data: List[Dict[str, Any]]) -> DocumentRiskScoreResult:
    """Rule-based document-level risk aggregation (Stage 2, no LLM) — this is
    the fast, Groq-quota-safe default computed automatically at ingestion.

    Replaces the original approach of concatenating every clause's full text
    into one LLM prompt (the primary source of the truncation/quota issues)
    with a weighted average of already-computed per-clause risk levels.
    """
    if not clauses_data:
        return DocumentRiskScoreResult(
            risk_score=0, risk_level="Low", affected_clauses=[],
            reasoning="No clauses were available to assess.", recommendations="N/A",
        )

    scored = []
    for i, row in enumerate(clauses_data):
        c = dict(row) if hasattr(row, "keys") else row
        section = c.get("section_name", f"Clause {i + 1}")
        level = c.get("risk_level", "None")
        # Prefer the real content-derived numeric score (analyzer_agent's
        # score_risk_points) when present; fall back to the fixed per-level
        # table for clauses persisted before that field existed.
        points = c["risk_score"] if c.get("risk_score") is not None else RISK_POINTS.get(level, 5)
        scored.append((section, c.get("classification", "General"), level, points))

    return _aggregate(document_name, scored, "rule-based phrase scan")


def assess_document_risk_with_llm(document_name: str, clauses_data: List[Dict[str, Any]]) -> DocumentRiskScoreResult:
    """On-demand LLM document-level risk aggregation — triggered only by the
    'Generate Document Risk Score' button (pages/risk_analysis.py), never
    during ingestion. Re-assesses every clause with a real LLM call (via
    analyzer_agent.analyze_clause_risk_with_llm) instead of the rule-based
    phrase scan, persists each corrected score back onto its clause record
    (so clause_analysis.py/risk_analysis.py's per-clause views reflect it
    too), then runs the same aggregation math as the rule-based path.

    Deliberately calls the LLM once PER CLAUSE rather than concatenating all
    clause text into a single prompt — that single-giant-prompt approach was
    the original cause of the truncation/quota errors this app used to hit.
    Per-clause prompts stay small regardless of document size; the tradeoff
    is wall-clock time (one Groq round trip per clause) instead of prompt
    size, which is why this is an explicit, on-demand action rather than
    something that runs automatically on every upload.
    """
    from agents.analyzer_agent import analyze_clause_risk_with_llm
    from database import crud

    if not clauses_data:
        return DocumentRiskScoreResult(
            risk_score=0, risk_level="Low", affected_clauses=[],
            reasoning="No clauses were available to assess.", recommendations="N/A",
        )

    scored = []
    for i, row in enumerate(clauses_data):
        c = dict(row) if hasattr(row, "keys") else row
        section = c.get("section_name", f"Clause {i + 1}")
        classification = c.get("classification", "General")
        text = c.get("text_content", "")
        clause_id = c.get("id")

        try:
            llm_result = analyze_clause_risk_with_llm(section, text)
            level, points = llm_result.risk_level, llm_result.risk_score
            if clause_id is not None:
                try:
                    crud.update_clause_risk(
                        clause_id=clause_id, risk_level=llm_result.risk_level,
                        risk_category=llm_result.risk_category, risk_score=llm_result.risk_score,
                        explanation=llm_result.explanation, source="LLM (document-level re-analysis)",
                    )
                except Exception:
                    logger.exception(f"Failed to persist LLM risk re-score for clause {clause_id}")
        except Exception as e:
            logger.warning(f"LLM risk assessment failed for clause '{section}', keeping prior score: {e}")
            level = c.get("risk_level", "None")
            points = c["risk_score"] if c.get("risk_score") is not None else RISK_POINTS.get(level, 5)

        scored.append((section, classification, level, points))

    return _aggregate(document_name, scored, "Groq LLM re-assessment of every clause")


def generate_risk_mitigation(section_name: str, clause_text: str, risk_level: str,
                              risk_category: str, explanation: str) -> str:
    """On-demand plain-English risk breakdown for a single clause — triggered
    by the "Simplify Risk" button (views/risk_analysis.py). Single-clause
    prompt built via services/prompt_builder, never the full document."""
    system_prompt = "You are an expert contract lawyer providing risk mitigation advice."
    instructions = (
        f"The following clause was flagged as having a {risk_level} risk "
        f"in the category '{risk_category}'.\n\n"
        f"Risk Explanation:\n{explanation}\n\n"
        "Write a plain-English risk breakdown using this exact Markdown structure:\n"
        "### Why It Is Risky\n<one short paragraph on the specific threat/exposure>\n\n"
        "### Legal Impact\n<1-2 sentences on legal exposure or enforceability risk>\n\n"
        "### Business Impact\n<1-2 sentences on operational/commercial impact>\n\n"
        "### Possible Consequences\n<3-5 bullet points, each starting with '✔ ', "
        "covering concrete downside scenarios>\n\n"
        "### Suggested Mitigation\n<a revised, markup-ready version of the clause text "
        "or concrete steps to reduce the risk>\n\n"
        "### AI Recommendation\n<1-2 short paragraphs recommending what to do next>"
    )
    user_prompt = build_clause_prompt(section_name, clause_text, instructions)
    return invoke_llm_text(system_prompt, user_prompt, temperature=0.2)


def generate_improved_clause(original_clause_text: str, mitigation_breakdown: str) -> str:
    """On-demand redraft of a single clause based on a prior risk-mitigation
    breakdown — triggered by "Generate Improved Clause" (views/risk_analysis.py).
    Single-clause prompt, never the full document."""
    system_prompt = "You are an expert contract lawyer redrafting a legal clause."
    user_prompt = (
        f"Based on this risk breakdown:\n\n{mitigation_breakdown}\n\n"
        "Rewrite the following clause so it fully addresses the risks and "
        "recommendations above. Return ONLY the revised clause text, no commentary.\n\n"
        f"Original Clause:\n{original_clause_text}"
    )
    return invoke_llm_text(system_prompt, user_prompt, temperature=0.2)
