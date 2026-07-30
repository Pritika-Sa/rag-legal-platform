from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from api.deps import get_current_user
from api.schemas.chat import ChatRequest, ChatResponse
from api.utils.ownership import get_owned_document

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest, current_user: dict = Depends(get_current_user)):
    """Mirrors app.py's floating chat handler: same call to
    agents.qa_agent.answer_legal_question, same str(doc_id)-or-None scoping.
    Ownership-checked when a doc_id is given — an HTTP endpoint can be asked
    to scope retrieval to *any* doc_id directly, a new attack surface
    Streamlit's session-embedded active_doc_id never exposed (same class of
    guard as every other document-scoped endpoint in this migration).
    LLM-bound, so run off the event loop (Migration Risk #1)."""
    if body.doc_id is not None:
        get_owned_document(body.doc_id, current_user["id"])

    from agents.qa_agent import answer_legal_question

    doc_id_str = str(body.doc_id) if body.doc_id is not None else None
    try:
        result = await run_in_threadpool(answer_legal_question, body.query, doc_id_str, current_user["id"])
    except Exception as e:
        # app.py catches this and appends "Failed to answer: {e}" as a
        # regular assistant message rather than an error state — the
        # frontend reproduces that exact text on catching this 500.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to answer: {e}")

    return ChatResponse(
        answer=result.answer,
        supporting_clauses=result.supporting_clauses,
        hallucination=result.hallucination,
    )
