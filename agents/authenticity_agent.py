"""Authenticity Detection Agent (Stage 2, no LLM) — deliberately separate
from risk_scoring_agent.py. Legal risk measures how dangerous a clause's
*content* is; authenticity measures whether the document is even a genuine,
complete, well-formed legal document in the first place. A fabricated
document with bland, low-risk-sounding clauses would score "low risk" and
still be fake — the two scores must never be blended.

This is the live entry point for the entropy-fused Document Authenticity
Index (see authenticity/) — replaces the old fixed-deduction scorer (flat
-20/-15/-10 points per failed check) the same way risk_engine/ replaced
agents.rule_engine.score_risk_points(): the old implementation is deleted
outright, not kept alongside the new one. Combines the original 7 generic
factors with an additive 8th layer of document-type-specific evidence
checks (authenticity/type_validators/) — the 7-factor pipeline itself is
unchanged; the 8th factor is simply not applicable for document types that
don't have a specific validator registered yet.

Each factor is called defensively (_safe()) — a single factor
crashing (a malformed file, a spaCy edge case) degrades that one factor to
"not applicable" rather than sinking the whole authenticity assessment,
since authenticity.dai.assess_document_authenticity already treats
not-applicable factors as "no evidence" and excludes them from fusion
rather than penalizing the document for them.
"""

import logging
from typing import Any, Dict, List, Optional
from types import SimpleNamespace

from pydantic import BaseModel, Field

from authenticity.clauses import assess_clause_completeness
from authenticity.cross_field import assess_cross_field_consistency
from authenticity.dai import assess_document_authenticity as _fuse_authenticity_factors
from authenticity.digital import assess_digital_verification
from authenticity.entities import assess_entity_verification
from authenticity.metadata import assess_metadata_validation
from authenticity.semantic import assess_semantic_consistency
from authenticity.structure import assess_structure
from authenticity.type_validators import assess_document_type_validators
from database import crud
from services.document_classifier import classify_document_type_ranked

logger = logging.getLogger(__name__)


class FactorSummary(BaseModel):
    name: str
    applicable: bool
    score: Optional[float] = Field(default=None, description="0-1. None when not applicable.")
    confidence: float = 0.0
    weight: Optional[float] = Field(default=None, description="Fusion weight, 0-1. None when not applicable (excluded from fusion).")
    evidence: List[str] = Field(default_factory=list)


class AuthenticityResult(BaseModel):
    authenticity_score: int = Field(description="0-100, 100 = fully authentic-looking (rounded DAI)")
    authenticity_level: str = Field(description="'Authentic' / 'Likely Authentic' / 'Suspicious' / 'Highly Suspicious' / 'Insufficient Signal'")
    confidence: float = Field(description="0-100")
    document_type: str
    document_type_confidence: float = Field(description="0-1, Stage 0 classification confidence")
    factors: List[FactorSummary] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list, description="Document-level fusion evidence: which factors were combined/skipped")


def _safe(name: str, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.exception(f"Authenticity factor '{name}' failed; treating as not applicable for this document.")
        return SimpleNamespace(
            applicable=False, score=0.0, confidence=0.0,
            evidence=[f"Factor '{name}' failed to compute and was excluded from this document's score."],
        )


def assess_document_authenticity(
    doc_name: str,
    clauses: List[Dict[str, Any]],
    full_text: str,
    file_path: Optional[str] = None,
    pages: Optional[List[Dict[str, Any]]] = None,
) -> AuthenticityResult:
    classification = classify_document_type_ranked(full_text)

    # Computed before the dict below (not inline) so the new document-type-
    # validator layer can reuse this factor's QR/signature-field findings
    # instead of re-scanning the PDF a second time.
    digital_result = _safe("digital_verification", assess_digital_verification, file_path)

    factor_results = {
        # clauses/pages threaded through (2026-07-20) so structure can also
        # score section-numbering order and cross-page continuity, not just
        # section presence — see authenticity/structure.py.
        "structure": _safe("structure", assess_structure, full_text, classification, clauses, pages or []),
        "clause_completeness": _safe("clause_completeness", assess_clause_completeness, clauses, classification),
        "cross_field": _safe("cross_field", assess_cross_field_consistency, full_text, classification),
        "entity_verification": _safe("entity_verification", assess_entity_verification, pages or []),
        "digital_verification": digital_result,
        "metadata_validation": _safe("metadata_validation", assess_metadata_validation, file_path),
        # document_type threaded through (2026-07-20) purely for
        # explainability text ("Structured Insurance Policy detected...") —
        # the structured-vs-prose branching itself is driven by the
        # document's own measured prose/field-clause ratio, never by this
        # type name, so no per-type logic is duplicated here.
        "semantic_consistency": _safe(
            "semantic_consistency", assess_semantic_consistency, clauses, classification.document_type,
        ),
        # Factor 8, additive on top of the original 7 (see authenticity/type_validators/):
        # deterministic, document-type-specific evidence checks (e.g. GST
        # arithmetic and IRDAI registration for an Insurance Policy) that have
        # no equivalent in the 7 generic factors above. Reports
        # applicable=False (not a penalty) for any document type without a
        # registered validator yet.
        "document_type_validator": _safe(
            "document_type_validator", assess_document_type_validators,
            classification.document_type, full_text, pages or [], clauses, digital_result,
        ),
    }

    dai_result = _fuse_authenticity_factors(factor_results)
    weight_by_name = {c.name: c.weight for c in dai_result.contributions}

    factors = [
        FactorSummary(
            name=name,
            applicable=result.applicable,
            score=round(float(result.score), 4) if result.applicable else None,
            confidence=result.confidence,
            weight=weight_by_name.get(name),
            evidence=result.evidence,
        )
        for name, result in factor_results.items()
    ]

    return AuthenticityResult(
        authenticity_score=round(dai_result.dai_score),
        authenticity_level=dai_result.authenticity_level,
        confidence=dai_result.confidence,
        document_type=classification.document_type,
        document_type_confidence=classification.confidence,
        factors=factors,
        evidence=dai_result.evidence,
    )


def assess_and_persist_document_authenticity(
    doc_id: int,
    doc_name: str,
    clauses: List[Dict[str, Any]],
    full_text: str,
    file_path: Optional[str] = None,
    pages: Optional[List[Dict[str, Any]]] = None,
) -> AuthenticityResult:
    """Runs assess_document_authenticity() and persists every field the
    Risk Analysis page's factor-breakdown toggle reads, in one place, so
    agents/orchestrator.py's authenticity_check_node (automatic, at
    ingestion) and views/risk_analysis.py's on-demand "Recompute
    Authenticity" button (for documents ingested before this engine went
    live, or whenever a fresh read is wanted) can't drift out of sync on
    which fields get saved."""
    result = assess_document_authenticity(doc_name, clauses, full_text, file_path=file_path, pages=pages)
    crud.update_document_analysis(
        doc_id,
        authenticity_score=result.authenticity_score,
        authenticity_level=result.authenticity_level,
        authenticity_confidence=result.confidence,
        authenticity_document_type=result.document_type,
        authenticity_document_type_confidence=result.document_type_confidence,
        authenticity_factors=[f.model_dump() for f in result.factors],
    )
    return result
