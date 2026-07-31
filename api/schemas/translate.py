from pydantic import BaseModel

from services.translation_service import DEFAULT_TARGET_LANGUAGE


class TranslateRequest(BaseModel):
    texts: list[str]
    target_language: str = DEFAULT_TARGET_LANGUAGE


class TranslateResponse(BaseModel):
    translations: list[str]
