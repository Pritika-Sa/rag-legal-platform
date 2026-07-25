from typing import Optional

from pydantic import BaseModel


class ComparisonRequest(BaseModel):
    doc_a_id: int
    doc_b_id: int


class ClauseForComparison(BaseModel):
    id: int
    section_name: str
    classification: Optional[str] = None
    text_content: str


class ComparisonResponse(BaseModel):
    doc_a_name: str
    doc_b_name: str
    similarity_score: int
    change_summary: str
    added_clauses: list[str]
    removed_clauses: list[str]
    modified_clauses: list[str]
    risk_changes: str
    difference_report: str
    clauses_a: list[ClauseForComparison]
    clauses_b: list[ClauseForComparison]
