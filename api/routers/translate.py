from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from api.deps import get_current_user
from api.schemas.translate import TranslateRequest, TranslateResponse
from services.translation_service import TranslationError, translate_texts

router = APIRouter(prefix="/api/translate", tags=["translate"])


@router.post("", response_model=TranslateResponse)
async def translate(body: TranslateRequest, current_user: dict = Depends(get_current_user)):
    """Presentation-layer only: translates already-generated response text
    for display. Never touches the RAG pipeline, MongoDB, or any agent —
    callers pass already-computed strings in and get translated strings
    back, nothing is read from or written to storage here. Network call,
    so run off the event loop like chat's LLM call."""
    try:
        translations = await run_in_threadpool(translate_texts, body.texts, body.target_language)
    except TranslationError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    return TranslateResponse(translations=translations)
