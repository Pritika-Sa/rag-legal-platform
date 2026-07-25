from typing import Any, Optional

from pydantic import BaseModel


class ClauseWithIntelligence(BaseModel):
    id: int
    section_name: str
    text_content: str
    classification: Optional[str] = None
    risk_category: Optional[str] = None
    risk_level: str
    simplification: Optional[str] = None
    importance_score: Optional[int] = None
    importance_category: str
    legal_impact: Optional[int] = None
    financial_impact: Optional[int] = None
    business_impact: Optional[int] = None
    compliance_impact: Optional[int] = None
    confidence_score: Optional[float] = None
    impact_chart: Optional[dict[str, Any]] = None


class SimplifyResponse(BaseModel):
    simplified_clause: str
    easy_summary: str
    rights: str
    obligations: str
    hidden_risks: str
    ai_recommendation: str
