from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from api.deps import get_current_user
from api.schemas.comparison import ClauseForComparison, ComparisonRequest, ComparisonResponse
from api.utils.ownership import get_owned_document
from database import crud

router = APIRouter(prefix="/api/comparison", tags=["comparison"])


@router.post("", response_model=ComparisonResponse)
async def compare(body: ComparisonRequest, current_user: dict = Depends(get_current_user)):
    """Mirrors views/comparison.py::render()'s "Compare Documents" handler:
    same two-different-documents guard, same per-document backfill, same
    compare_documents call, same audit log entry. Comparison never touches
    the global active document — it keeps its own selection, same as the
    original."""
    if body.doc_a_id == body.doc_b_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Please select two different documents to compare."
        )

    doc_a = get_owned_document(body.doc_a_id, current_user["id"])
    doc_b = get_owned_document(body.doc_b_id, current_user["id"])

    from agents.clause_identifier_agent import backfill_clause_titles_for_document

    for doc_id, doc in ((body.doc_a_id, doc_a), (body.doc_b_id, doc_b)):
        if not doc.get("clause_titles_backfilled"):
            backfill_clause_titles_for_document(doc_id)
            crud.update_document_analysis(doc_id, clause_titles_backfilled=True)

    clauses_a = crud.get_clauses_for_document(body.doc_a_id)
    clauses_b = crud.get_clauses_for_document(body.doc_b_id)

    from agents.comparison_agent import compare_documents

    # 2026-07-27 clause-extraction fix: structured/metadata fields (Policy
    # Number, IDV, Nominee Name, ...) are excluded from the actual
    # comparison -- diffing two policy-schedule table rows as if they were
    # competing legal clauses produced meaningless "added/removed/modified
    # clause" noise. clauses_a/clauses_b themselves stay unfiltered below,
    # so structured fields remain visible in the comparison UI's raw clause
    # lists; only the analysis input is filtered.
    legal_clauses_a = [c for c in clauses_a if c.get("classification") != "Structured Field"]
    legal_clauses_b = [c for c in clauses_b if c.get("classification") != "Structured Field"]

    result = await run_in_threadpool(compare_documents, legal_clauses_a, legal_clauses_b, doc_a["name"], doc_b["name"])

    crud.add_audit_log("compare_documents", f"Compared {doc_a['name']} and {doc_b['name']} with Agent 10")

    return ComparisonResponse(
        doc_a_name=doc_a["name"],
        doc_b_name=doc_b["name"],
        similarity_score=result.similarity_score,
        change_summary=result.change_summary,
        added_clauses=result.added_clauses,
        removed_clauses=result.removed_clauses,
        modified_clauses=result.modified_clauses,
        risk_changes=result.risk_changes,
        difference_report=result.difference_report,
        clauses_a=[
            ClauseForComparison(
                id=c["id"], section_name=c["section_name"], classification=c.get("classification"),
                text_content=c.get("text_content") or "",
            )
            for c in clauses_a
        ],
        clauses_b=[
            ClauseForComparison(
                id=c["id"], section_name=c["section_name"], classification=c.get("classification"),
                text_content=c.get("text_content") or "",
            )
            for c in clauses_b
        ],
    )
