"""Data contracts for the Hybrid Explainable Risk Engine.

`LegalFeatureVector` is the interface boundary between NLP feature
extraction and risk scoring: the engine never parses clause text itself or
runs its own regex/keyword matching to decide risk — it only consumes this
structured schema. Today these are built by hand (or by tests); a later
`agents/feature_extraction_agent.py` populates them from real NER/
dependency-parse output without this package changing at all.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Polarity(str, Enum):
    OBLIGATION = "obligation"
    RIGHT = "right"
    PROHIBITION = "prohibition"


class Entity(BaseModel):
    text: str
    entity_type: str
    confidence: float = 1.0


class Obligation(BaseModel):
    """One subject-modal-action triple with its grammatical polarity.
    `modal` is a closed grammatical class (shall/must/may/should/...) used
    only to classify obligation vs right vs prohibition — it carries no
    risk weight of its own."""
    subject: str
    modal: str
    polarity: Polarity
    action: str
    confidence: float = 1.0


class FinancialTerm(BaseModel):
    amount: Optional[float] = None
    currency: Optional[str] = None
    is_percentage: bool = False
    is_capped: Optional[bool] = None  # None = unknown / not applicable


class Deadline(BaseModel):
    kind: str  # "date" | "duration"
    value: str
    normalized_days: Optional[float] = None


class LegalAction(BaseModel):
    """Zero-shot/fine-tuned clause-action classification output, e.g.
    'termination', 'indemnification', 'waiver', 'compliance'."""
    action_type: str
    confidence: float = 1.0


class Dependency(BaseModel):
    target_clause_id: Optional[int] = None
    relation: str
    confidence: float = 1.0


class LegalFeatureVector(BaseModel):
    clause_id: int
    entities: List[Entity] = Field(default_factory=list)
    obligations: List[Obligation] = Field(default_factory=list)
    deadlines: List[Deadline] = Field(default_factory=list)
    financial_terms: List[FinancialTerm] = Field(default_factory=list)
    legal_actions: List[LegalAction] = Field(default_factory=list)
    jurisdiction: Optional[str] = None
    dependencies: List[Dependency] = Field(default_factory=list)
    has_prose_verb: Optional[bool] = Field(
        default=None,
        description="True if the clause contains at least one finite verb/auxiliary "
                     "(spaCy POS VERB or AUX) anywhere, i.e. is prose attempting to state "
                     "something, as opposed to a structured/tabular data field (a label, a "
                     "key:value row) that was never prose to begin with. None means unknown "
                     "(not computed by the caller, e.g. a hand-built or pre-Sprint-2B vector) "
                     "and is treated as prose by risk_engine.dimensions._ambiguity_feature_signal "
                     "for backward compatibility. Populated by "
                     "agents.feature_extraction_agent.extract_legal_features; feeds only the "
                     "Ambiguity dimension's feature signal (Sprint 2B, Issue 1) — no other "
                     "dimension reads this field.",
    )


class ClauseInput(BaseModel):
    """What the engine actually scores: a clause's id/text (text is needed
    only for embedding — the engine still never regex/keyword-scans it) plus
    its pre-extracted LegalFeatureVector."""
    clause_id: int
    text: str
    features: LegalFeatureVector


class DimensionScore(BaseModel):
    dimension: str
    feature_signal: float  # F_d, in [0,1]
    semantic_signal: float  # E_d, in [0,1]
    alpha: float  # feature/semantic trust coefficient used to fuse F_d and E_d for this document (fusion.dynamic_alpha)
    score: float  # S_d(c) = fuse(F_d, E_d), in [0,1]
    weight: float  # entropy-derived w_d for this document, in [0,1]
    contribution: float  # weight * score * 100 — points out of the LRSI 0-100 total
    feature_evidence: List[str] = Field(default_factory=list)
    semantic_evidence: Optional[Dict[str, Any]] = None  # {"prototype": str, "similarity": float}


class RiskAssessment(BaseModel):
    clause_id: int
    lrsi: float  # 0-100
    classification: str  # "Low" | "Medium" | "High"
    confidence: float  # 0-100
    dimension_breakdown: List[DimensionScore]


class DocumentRiskAssessment(BaseModel):
    clause_assessments: List[RiskAssessment]
    dimension_weights: Dict[str, float]  # entropy-derived weights used for this document, sums to ~1
    dimension_alphas: Dict[str, float] = Field(
        default_factory=dict,
        description="Feature/semantic trust coefficient used per dimension for this document (fusion.dynamic_alpha)",
    )
    confidence_weights: Dict[str, float] = Field(
        default_factory=dict,
        description="Entropy-derived weights (agreement/feature_confidence/margin) combining each clause's confidence score for this document",
    )
    average_lrsi: float
    document_risk_score: float  # Gini-adjusted document-level aggregate
    high_count: int
    medium_count: int
    low_count: int
