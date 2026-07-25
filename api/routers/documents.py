from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from api.deps import get_current_user
from api.schemas.documents import (
    DashboardResponse,
    DocumentSummary,
    ProcessRequest,
    ProcessResponse,
    UploadResponse,
)
from api.utils.charts import figure_to_json
from api.utils.ownership import get_owned_document
from api.utils.uploads import save_uploaded_file
from database import crud
from utils import visualizer

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentSummary])
def list_documents(current_user: dict = Depends(get_current_user)):
    # Search filtering and delete remain later-phase scope (Phase 4 covers
    # delete alongside Processing); this list is already what both the
    # Phase 2 dashboard selector and the Phase 3 upload panel need.
    return crud.get_all_documents(user_id=current_user["id"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile, current_user: dict = Depends(get_current_user)):
    # Mirrors app.py's sidebar upload block: writes the file to disk and
    # returns its path — it does NOT create a documents collection entry or
    # appear in the sidebar list yet. In the original app that only happens
    # once "Process Document" runs agents.orchestrator.run_orchestration
    # (Phase 4), which is the first thing that calls crud.add_document.
    file_path = await save_uploaded_file(file, current_user["id"])
    return UploadResponse(file_path=file_path, name=file.filename)


@router.get("/{doc_id}/dashboard", response_model=DashboardResponse)
def get_dashboard(doc_id: int, current_user: dict = Depends(get_current_user)):
    document = get_owned_document(doc_id, current_user["id"])

    # Mirrors views/dashboard.py::render() exactly: same crud calls, same
    # "Unknown Document" fallback, same clauses-empty guard around chart
    # generation.
    metrics = crud.get_dashboard_metrics(doc_id=doc_id, user_id=current_user["id"])
    clauses = crud.get_clauses_for_document(doc_id=doc_id)
    doc_type_display = document.get("document_type") or "Unknown Document"

    radar_chart = None
    bar_chart = None
    if clauses:
        radar_chart = figure_to_json(visualizer.generate_risk_radar_chart(metrics["risk_distribution"]))
        bar_chart = figure_to_json(visualizer.generate_category_bar_chart(clauses))

    return DashboardResponse(
        total_clauses=metrics["total_clauses"],
        risky_clauses=metrics["risky_clauses"],
        total_contradictions=metrics["total_contradictions"],
        document_type=doc_type_display,
        risk_distribution=metrics["risk_distribution"],
        radar_chart=radar_chart,
        bar_chart=bar_chart,
    )


@router.post("/process", response_model=ProcessResponse)
async def process_document(body: ProcessRequest, current_user: dict = Depends(get_current_user)):
    """Mirrors app.py's "Process Document" button handler branch-for-branch:
    same three outcomes (already-analyzed / failed / success), same crud
    calls, same audit log entry. run_orchestration is a synchronous,
    LLM-bound call (Migration Risk #1 in the plan) — run off the event loop
    via run_in_threadpool so one slow analysis doesn't stall every other
    request this worker is handling."""
    from agents.orchestrator import run_orchestration

    try:
        result = await run_in_threadpool(run_orchestration, body.file_path, user_id=current_user["id"])
    except RuntimeError as e:
        # e.g. OCR engine not found — same user-facing case app.py catches
        # separately from a generic Exception.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    error = result.get("error")
    if error and "already analyzed" in error.lower():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "This document has already been analyzed.", "doc_id": result["doc_id"]},
        )
    if error:
        if result.get("doc_id"):
            crud.update_document_analysis(result["doc_id"], status="failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Analysis failed: {error}")

    crud.update_document_analysis(result["doc_id"], status="processed")
    crud.add_audit_log("analysis_completed", f"Completed multi-agent processing for '{body.name}'")

    return ProcessResponse(
        doc_id=result["doc_id"],
        clause_count=len(result.get("db_clauses", [])),
        document_risk_score=result.get("document_risk_score", 0),
        authenticity_score=result.get("authenticity_score", 0),
        parsing_quality_warning=result.get("parsing_quality_warning"),
    )


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: int, current_user: dict = Depends(get_current_user)):
    get_owned_document(doc_id, current_user["id"])
    crud.delete_document(doc_id)
