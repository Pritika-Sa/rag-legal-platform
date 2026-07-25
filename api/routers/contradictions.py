from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from api.deps import get_current_user
from api.schemas.contradictions import Contradiction
from api.utils.ownership import get_owned_document
from database import crud

router = APIRouter(prefix="/api/documents", tags=["contradictions"])


def _run_and_persist_ai_pass(doc_id: int, clauses: list) -> None:
    """Identical to views/contradiction.py's _run_and_persist_ai_pass: full
    hybrid pipeline (rules + embeddings + LLM verification), written over
    whatever's currently persisted, flagged so it only auto-runs once."""
    from agents.contradiction_agent import find_contradictions

    contradictions = find_contradictions(clauses, use_llm=True)
    crud.replace_contradictions_for_document(doc_id, contradictions)
    crud.update_document_analysis(doc_id, contradiction_ai_analyzed=True)


@router.get("/{doc_id}/contradictions", response_model=list[Contradiction])
async def get_contradictions(doc_id: int, current_user: dict = Depends(get_current_user)):
    """Mirrors views/contradiction.py::render() exactly: same one-time
    clause-title backfill, same auto-triggered one-time AI pass on first
    visit (including titles_just_backfilled forcing a redo, since a backfill
    invalidates any contradictions computed against the old bare-category
    titles). LLM-bound, so run off the event loop (Migration Risk #1)."""
    document = get_owned_document(doc_id, current_user["id"])
    clauses = crud.get_clauses_for_document(doc_id)

    titles_just_backfilled = False
    if clauses and not document.get("clause_titles_backfilled"):
        from agents.clause_identifier_agent import backfill_clause_titles_for_document

        if backfill_clause_titles_for_document(doc_id):
            clauses = crud.get_clauses_for_document(doc_id)
            titles_just_backfilled = True
        crud.update_document_analysis(doc_id, clause_titles_backfilled=True)
        document = crud.get_document_by_id(doc_id)

    ai_analyzed = bool(document.get("contradiction_ai_analyzed"))
    if not ai_analyzed or titles_just_backfilled:
        await run_in_threadpool(_run_and_persist_ai_pass, doc_id, clauses)

    return crud.get_contradictions_for_document(doc_id)


@router.post("/{doc_id}/contradictions/reanalyze", response_model=list[Contradiction])
async def reanalyze_contradictions(doc_id: int, current_user: dict = Depends(get_current_user)):
    get_owned_document(doc_id, current_user["id"])
    clauses = crud.get_clauses_for_document(doc_id)
    await run_in_threadpool(_run_and_persist_ai_pass, doc_id, clauses)
    return crud.get_contradictions_for_document(doc_id)
