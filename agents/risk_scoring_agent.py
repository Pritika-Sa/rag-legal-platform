import logging
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Tuple

import numpy as np

from risk_engine import fusion
from risk_engine.thresholds import DEFAULT_DOCUMENT_CUTS
from services.prompt_builder import build_clause_prompt
from utils.llm_client import invoke_llm_text

logger = logging.getLogger(__name__)

# Fallback only, for clauses persisted before per-clause risk_score existed
# (or if a re-score attempt fails) — every clause processed by the current
# pipeline (agents/analyzer_agent.assess_clauses_batch) always has a real
# LRSI risk_score, so this table is legacy-data safety net, not a scoring
# table in active use.
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


def _aggregate(document_name: str, scored: List[tuple], method_note: str,
                document_thresholds: Optional[Tuple[float, float, float]] = None) -> DocumentRiskScoreResult:
    """Shared aggregation math for both the engine-based and LLM-based
    paths: mean of per-clause LRSI scores, scaled up by a Gini-coefficient
    concentration term (risk_engine.fusion.document_risk_score) rather than
    the old fixed '+10 if >30% of clauses are High risk' step function —
    the Gini coefficient is a continuous, established inequality statistic,
    so a document where risk is concentrated in a few severe clauses scores
    higher than one with the same average spread evenly, without an
    arbitrary threshold.

    `document_thresholds` (low_medium, medium_high, high_critical cuts) is
    injectable for tests; real callers leave it None and get the shared
    ThresholdRegistry's Jenks-derived cuts (agents.analyzer_agent), falling
    back to DEFAULT_DOCUMENT_CUTS until enough documents have been scored."""
    total = len(scored)
    points_array = np.array([points for _, _, _, points in scored], dtype=float)
    high_count = sum(1 for _, _, level, _ in scored if level == "High")
    high_ratio = high_count / total

    risk_score = max(0, min(100, round(fusion.document_risk_score(points_array))))

    if document_thresholds is None:
        from agents.analyzer_agent import _get_threshold_registry
        document_thresholds = _get_threshold_registry().document_thresholds().cuts
    low_medium_cut, medium_high_cut, high_critical_cut = document_thresholds
    risk_level = fusion.classify_4tier(risk_score, low_medium_cut, medium_high_cut, high_critical_cut)

    top_contributors = sorted(scored, key=lambda s: s[3], reverse=True)[:5]
    affected_clauses = [section for section, _, level, _ in top_contributors if level in ("High", "Medium")]

    reasoning = (
        f"{document_name}: {total} clauses assessed, {high_count} at High risk "
        f"({round(high_ratio * 100)}%). Aggregate score {risk_score}/100 derived from the mean "
        f"per-clause risk score ({method_note}), scaled by how concentrated risk is across "
        f"clauses (Gini coefficient of the score distribution)."
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
    """Document-level risk aggregation over already-scored clauses (Stage 2,
    no LLM, no re-extraction) — this is the fast, Groq-quota-safe default
    computed automatically at ingestion (agents/orchestrator.py), and also
    callable on demand (the "Quick Estimate" action in views/risk_analysis.py)
    since it's pure aggregation math over each clause's already-computed
    risk_score, never a re-run of feature extraction or embeddings.

    Every `risk_score` here originates from the Hybrid Explainable Risk
    Engine's per-clause LRSI (agents.analyzer_agent.assess_clauses_batch) —
    this function only aggregates it up to document level.
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
        # Prefer the real content-derived LRSI (assess_clauses_batch) when
        # present; fall back to the fixed per-level table for clauses
        # persisted before that field existed.
        points = c["risk_score"] if c.get("risk_score") is not None else RISK_POINTS.get(level, 5)
        scored.append((section, c.get("classification", "General"), level, points))

    return _aggregate(document_name, scored, "Hybrid Explainable Risk Engine LRSI")


def assess_document_risk_with_llm(document_name: str, clauses_data: List[Dict[str, Any]]) -> DocumentRiskScoreResult:
    """On-demand LLM document-level risk aggregation — triggered only by the
    'Generate Document Risk Score' button (pages/risk_analysis.py), never
    during ingestion. Re-assesses every clause with a real LLM call (via
    analyzer_agent.analyze_clause_risk_with_llm) instead of the automatic
    Hybrid Explainable Risk Engine pass, persists each corrected score
    back onto its clause record
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
