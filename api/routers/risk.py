from fastapi import APIRouter, Depends

from agents.importance_agent import assess_clause_importance
from agents.rule_engine import detect_clause_type
from api.deps import get_current_user
from api.schemas.risk import QuickEstimateResponse, RiskOverviewResponse, RiskyClause
from api.utils.charts import figure_to_json
from api.utils.ownership import get_owned_document
from database import crud
from utils.visualizer import generate_risk_gauge_chart

router = APIRouter(prefix="/api/documents", tags=["risk"])


def _run_backfill_if_needed(doc_id: int, document: dict, clauses: list) -> list:
    """Shared one-time upgrade, same as clauses.py — a document-level flag,
    so whichever page (Clause Analysis, Risk Analysis, Contradiction) the
    user opens first runs it, and it's a harmless no-op for every page after
    that."""
    if clauses and not document.get("clause_titles_backfilled"):
        from agents.clause_identifier_agent import backfill_clause_titles_for_document

        if backfill_clause_titles_for_document(doc_id):
            clauses = crud.get_clauses_for_document(doc_id)
        crud.update_document_analysis(doc_id, clause_titles_backfilled=True)
    return clauses


@router.get("/{doc_id}/risk-overview", response_model=RiskOverviewResponse)
def get_risk_overview(doc_id: int, current_user: dict = Depends(get_current_user)):
    """Mirrors views/risk_analysis.py's Overview section: a passive read of
    the authenticity fields already persisted on the document (from
    ingestion or a prior "Recompute Authenticity" click) — no computation
    here, same as the original."""
    document = get_owned_document(doc_id, current_user["id"])
    return RiskOverviewResponse(
        authenticity_score=document.get("authenticity_score"),
        authenticity_level=document.get("authenticity_level", "Unknown"),
        authenticity_document_type=document.get("authenticity_document_type"),
        authenticity_document_type_confidence=document.get("authenticity_document_type_confidence"),
        authenticity_confidence=document.get("authenticity_confidence"),
        authenticity_factors=document.get("authenticity_factors"),
    )


@router.post("/{doc_id}/authenticity/recompute", response_model=RiskOverviewResponse)
def recompute_authenticity(doc_id: int, current_user: dict = Depends(get_current_user)):
    """Mirrors the "Recompute Authenticity" button exactly: same full_text
    join, same assess_and_persist_document_authenticity call, then reads the
    freshly persisted fields back — avoids needing to know
    AuthenticityResult's exact attribute names since the same function
    already wrote them to the document."""
    document = get_owned_document(doc_id, current_user["id"])
    clauses = crud.get_clauses_for_document(doc_id)

    from agents.authenticity_agent import assess_and_persist_document_authenticity

    full_text = "\n\n".join(f"{c.get('section_name') or ''}\n{c.get('text_content') or ''}" for c in clauses)
    pages = crud.get_pages_for_document(doc_id)
    assess_and_persist_document_authenticity(
        doc_id, document["name"], clauses, full_text, file_path=document.get("path"), pages=pages,
    )

    updated = crud.get_document_by_id(doc_id)
    return RiskOverviewResponse(
        authenticity_score=updated.get("authenticity_score"),
        authenticity_level=updated.get("authenticity_level", "Unknown"),
        authenticity_document_type=updated.get("authenticity_document_type"),
        authenticity_document_type_confidence=updated.get("authenticity_document_type_confidence"),
        authenticity_confidence=updated.get("authenticity_confidence"),
        authenticity_factors=updated.get("authenticity_factors"),
    )


@router.post("/{doc_id}/risk/quick-estimate", response_model=QuickEstimateResponse)
def quick_estimate(doc_id: int, current_user: dict = Depends(get_current_user)):
    document = get_owned_document(doc_id, current_user["id"])
    clauses = crud.get_clauses_for_document(doc_id)

    from agents.risk_scoring_agent import assess_document_risk

    result = assess_document_risk(document["name"], clauses)

    # Persist the just-displayed result as the document's canonical risk
    # score/level: Quick Estimate re-aggregates over each clause's *current*
    # risk_score/risk_level, which can have moved on from whatever was
    # persisted at ingestion time (agents/orchestrator.py, run once). Without
    # this, the Dashboard/chatbot/Risk Overview (all Mongo readers) keep
    # showing the stale ingestion-time value forever, even though this is
    # the number the user just saw on screen. Same aggregation function,
    # same inputs — this only writes its output, never recomputes it.
    crud.update_document_analysis(
        doc_id,
        document_risk_score=result.risk_score,
        document_risk_level=result.risk_level,
        document_risk_recommendations=result.recommendations,
    )

    return QuickEstimateResponse(
        risk_score=result.risk_score,
        risk_level=result.risk_level,
        recommendations=result.recommendations,
        risk_gauge_chart=figure_to_json(generate_risk_gauge_chart(result.risk_score)),
    )


@router.get("/{doc_id}/risky-clauses", response_model=list[RiskyClause])
def get_risky_clauses(doc_id: int, current_user: dict = Depends(get_current_user)):
    """Mirrors the Flagged Clauses section: same High/Medium filter, same
    _compute_display_intel (importance category + identification confidence,
    rule-based, no LLM) computed only for the risky subset. Category/level
    filtering happens client-side, same as the original."""
    document = get_owned_document(doc_id, current_user["id"])
    clauses = crud.get_clauses_for_document(doc_id)
    clauses = _run_backfill_if_needed(doc_id, document, clauses)

    risky = [c for c in clauses if c.get("risk_level") in ("High", "Medium")]

    result = []
    for c in risky:
        section_name = c.get("section_name") or "Clause"
        text = c.get("text_content") or ""
        try:
            importance_category = assess_clause_importance(section_name, text).importance_category
        except Exception:
            importance_category = None
        try:
            _clause_type, confidence = detect_clause_type(f"{section_name}\n{text}")
        except Exception:
            confidence = None

        result.append(
            RiskyClause(
                id=c["id"],
                section_name=c["section_name"],
                text_content=text,
                risk_level=c["risk_level"],
                risk_category=c.get("risk_category"),
                explanation=c.get("explanation"),
                dimension_breakdown=c.get("dimension_breakdown") or [],
                importance_category=importance_category,
                confidence_score=confidence,
            )
        )
    return result
