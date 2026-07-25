import statistics

from fastapi import APIRouter, Depends, HTTPException, status

from agents.impact_agent import analyze_clause_impact
from agents.importance_agent import assess_clause_importance
from agents.rule_engine import detect_clause_type
from api.deps import get_current_user
from api.schemas.clauses import ClauseWithIntelligence, SimplifyResponse
from api.utils.charts import figure_to_json
from api.utils.ownership import get_owned_document
from database import crud
from utils.visualizer import generate_clause_impact_radar_chart

router = APIRouter(prefix="/api/documents", tags=["clauses"])


@router.get("/{doc_id}/clauses", response_model=list[ClauseWithIntelligence])
def get_clauses(doc_id: int, current_user: dict = Depends(get_current_user)):
    """Mirrors views/clause_analysis.py::render()'s data-prep exactly: the
    same one-time clause-title backfill, and the same eager per-clause
    intelligence computation (compute_clause_intelligence there was already
    unconditional/eager — rule-based, no LLM, cheap — and its st.cache_data
    decorator only memoized identical input, it didn't defer the work).
    Every field here comes from calling the same backend functions with the
    same arguments; filtering happens client-side, exactly like Streamlit's
    own plain-Python list filtering did."""
    document = get_owned_document(doc_id, current_user["id"])

    clauses = crud.get_clauses_for_document(doc_id)
    if clauses and not document.get("clause_titles_backfilled"):
        from agents.clause_identifier_agent import backfill_clause_titles_for_document

        if backfill_clause_titles_for_document(doc_id):
            clauses = crud.get_clauses_for_document(doc_id)
        crud.update_document_analysis(doc_id, clause_titles_backfilled=True)

    result = []
    for c in clauses:
        section_name = c.get("section_name") or "Clause"
        text = c.get("text_content") or ""

        try:
            importance = assess_clause_importance(section_name, text)
        except Exception:
            importance = None
        try:
            impact = analyze_clause_impact(section_name, text)
        except Exception:
            impact = None
        try:
            _clause_type, confidence = detect_clause_type(f"{section_name}\n{text}")
        except Exception:
            confidence = None

        impact_chart = None
        if impact is not None:
            scores = [
                v
                for v in (impact.legal_impact, impact.financial_impact, impact.business_impact, impact.compliance_impact)
                if v is not None
            ]
            impact_score = round(statistics.mean(scores)) if scores else None
            if impact_score is not None and impact.legal_impact is not None:
                fig = generate_clause_impact_radar_chart(impact_score, impact.business_impact, impact.legal_impact)
                impact_chart = figure_to_json(fig)

        result.append(
            ClauseWithIntelligence(
                id=c["id"],
                section_name=c["section_name"],
                text_content=text,
                classification=c.get("classification"),
                risk_category=c.get("risk_category"),
                risk_level=c.get("risk_level") or "None",
                simplification=c.get("simplification"),
                importance_score=importance.importance_score if importance else None,
                importance_category=importance.importance_category if importance else "Informational",
                legal_impact=impact.legal_impact if impact else None,
                financial_impact=impact.financial_impact if impact else None,
                business_impact=impact.business_impact if impact else None,
                compliance_impact=impact.compliance_impact if impact else None,
                confidence_score=confidence,
                impact_chart=impact_chart,
            )
        )
    return result


@router.post("/{doc_id}/clauses/{clause_id}/simplify", response_model=SimplifyResponse)
def simplify_clause_endpoint(doc_id: int, clause_id: int, current_user: dict = Depends(get_current_user)):
    """Deliberately nested under /documents/{doc_id}/ rather than a bare
    /api/clauses/{id}, unlike the migration plan's original sketch — crud.py
    has no get_clause_by_id, only get_clauses_for_document, and adding one
    would be a backend change outside the adapter's remit. Looking the
    clause up within its (ownership-checked) document's own clause list
    uses only the existing, unmodified crud function."""
    get_owned_document(doc_id, current_user["id"])

    clauses = crud.get_clauses_for_document(doc_id)
    clause = next((c for c in clauses if c["id"] == clause_id), None)
    if clause is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clause not found.")

    from agents.simplification_agent import simplify_clause

    result = simplify_clause(clause.get("text_content") or "")
    return SimplifyResponse(
        simplified_clause=result.simplified_clause,
        easy_summary=result.easy_summary,
        rights=result.rights,
        obligations=result.obligations,
        hidden_risks=result.hidden_risks,
        ai_recommendation=result.ai_recommendation,
    )
