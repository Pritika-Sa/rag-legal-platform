from typing import Any, Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    doc_id: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    supporting_clauses: list[str]
    # Deliberately loose (matches QAResult.hallucination's own Any typing —
    # see agents/qa_agent.py's comment on why): can be None, or a dict whose
    # exact keys vary by whether the hallucination check itself succeeded.
    hallucination: Optional[dict[str, Any]] = None
