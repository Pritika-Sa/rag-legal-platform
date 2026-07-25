from typing import Optional

from pydantic import BaseModel


class AffectedClause(BaseModel):
    id: Optional[int] = None
    section_name: str
    text_content: str
    value: Optional[str] = None


class Contradiction(BaseModel):
    id: int
    contradiction_type: Optional[str] = None
    explanation: Optional[str] = None
    resolution: Optional[str] = None
    severity: Optional[str] = None
    affected_clauses: list[AffectedClause] = []
