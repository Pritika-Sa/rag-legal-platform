from typing import Any, Optional

from pydantic import BaseModel


class RiskOverviewResponse(BaseModel):
    authenticity_score: Optional[float] = None
    authenticity_level: str = "Unknown"
    authenticity_document_type: Optional[str] = None
    authenticity_document_type_confidence: Optional[float] = None
    authenticity_confidence: Optional[float] = None
    authenticity_factors: Optional[list[dict[str, Any]]] = None


class QuickEstimateResponse(BaseModel):
    risk_score: float
    risk_level: str
    recommendations: str
    risk_gauge_chart: dict[str, Any]


class RiskyClause(BaseModel):
    id: int
    section_name: str
    text_content: str
    risk_level: str
    risk_category: Optional[str] = None
    explanation: Optional[str] = None
    dimension_breakdown: list[dict[str, Any]] = []
    importance_category: Optional[str] = None
    confidence_score: Optional[float] = None
