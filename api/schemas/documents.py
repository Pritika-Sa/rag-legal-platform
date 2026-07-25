from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    id: int
    name: str
    status: str
    upload_date: Optional[datetime] = None
    document_type: Optional[str] = None


class UploadResponse(BaseModel):
    file_path: str
    name: str


class ProcessRequest(BaseModel):
    file_path: str
    name: str


class ProcessResponse(BaseModel):
    doc_id: int
    clause_count: int
    document_risk_score: float
    authenticity_score: float
    parsing_quality_warning: Optional[str] = None


class DashboardResponse(BaseModel):
    total_clauses: int
    risky_clauses: int
    total_contradictions: int
    document_type: str
    risk_distribution: dict[str, int]
    radar_chart: Optional[dict[str, Any]] = None
    bar_chart: Optional[dict[str, Any]] = None
