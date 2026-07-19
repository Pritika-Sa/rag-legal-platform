from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field

from agents.rule_engine import detect_clause_type, extract_obligations, extract_section_refs
from risk_engine.hybrid_engine import HybridExplainableRiskEngine
from risk_engine.schemas import ClauseInput as RiskClauseInput
from risk_engine.schemas import DimensionScore, DocumentRiskAssessment
from risk_engine.thresholds import ThresholdRegistry
from utils.llm_client import invoke_llm_structured


class EntityRelation(BaseModel):
    source: str = Field(description="The source entity or party")
    relation: str = Field(description="The action or link, e.g., 'must pay', 'indemnifies'")
    target: str = Field(description="The target entity, party, or location")


class ClauseAnalysisResult(BaseModel):
    classification: str = Field(description="The clause classification (e.g., Liability, Termination, Confidentiality)")
    risk_category: str = Field(
        description="The dimension that contributed most to this clause's LRSI "
                     "(Financial, Legal, Compliance, Operational, or Ambiguity)"
    )
    risk_level: str = Field(description="Severity: High, Medium, or Low")
    risk_score: int = Field(default=0, description="Legal Risk Severity Index (LRSI), 0-100")
    confidence: int = Field(default=0, description="0-100 confidence in this risk assessment")
    dimension_breakdown: List[DimensionScore] = Field(
        default_factory=list,
        description="Per-dimension score/weight/contribution/evidence — the full explainability record",
    )
    explanation: str = Field(description="Why this risk level was assigned and the legal implications")
    entities: List[EntityRelation] = Field(description="Extracted key entities and their relationships")
    dependencies: List[str] = Field(description="Any section names or numbers that this clause references")


_risk_engine_instance = None
_threshold_registry_instance = None


def _get_threshold_registry() -> ThresholdRegistry:
    """Lazy-loads and caches the ThresholdRegistry singleton — shared by
    the clause-level classification here (via _get_risk_engine) and the
    document-level classification in risk_scoring_agent._aggregate, so
    both draw Jenks-derived cut points from the same reference-data snapshot
    rather than each hitting MongoDB independently. Call
    .refresh_clause_thresholds()/.refresh_document_thresholds() on this
    instance to recalibrate against newer data without restarting the
    process."""
    global _threshold_registry_instance
    if _threshold_registry_instance is None:
        from database import crud
        _threshold_registry_instance = ThresholdRegistry(
            fetch_clause_scores=crud.get_recent_clause_risk_scores,
            fetch_document_scores=crud.get_recent_document_risk_scores,
        )
    return _threshold_registry_instance


def _get_risk_engine() -> HybridExplainableRiskEngine:
    """Lazy-loads and caches the HybridExplainableRiskEngine singleton
    (matches get_embeddings()/_get_reranker() elsewhere in the repo) — its
    PrototypeStore embeds every risk_engine/prototypes.json sentence once at
    construction, so building a fresh instance per document would re-embed
    the same ~13 sentences on every upload for no reason."""
    global _risk_engine_instance
    if _risk_engine_instance is None:
        from services.semantic_similarity import embed_texts
        registry = _get_threshold_registry()
        _risk_engine_instance = HybridExplainableRiskEngine(
            embed_fn=embed_texts,
            get_clause_thresholds=lambda: registry.clause_thresholds().cuts,
        )
    return _risk_engine_instance


def _build_explanation(assessment) -> str:
    """Human-readable paragraph built directly from the LRSI dimension
    breakdown (risk_engine.explain.build_dimension_breakdown) — replaces the
    old phrase-arithmetic readout ("'without notice' +15; base tier
    'Medium' = 55") with a plain statement of which dimensions drove the
    score and why. There is no point arithmetic to report anymore: every
    number here is either the LRSI itself or a dimension's exact additive
    contribution to it."""
    lines = [
        f"Legal Risk Severity Index: {assessment.lrsi:.0f}/100 ({assessment.classification}), "
        f"confidence {assessment.confidence:.0f}/100."
    ]
    for dim in assessment.dimension_breakdown[:3]:
        if dim.contribution <= 0:
            continue
        reason_bits = []
        if dim.feature_evidence:
            reason_bits.append(dim.feature_evidence[0])
        if dim.semantic_evidence and dim.semantic_evidence.get("prototype"):
            reason_bits.append(f"reads similarly to: \"{dim.semantic_evidence['prototype']}\"")
        reason = "; ".join(reason_bits) or "no specific evidence surfaced"
        lines.append(f"{dim.dimension} risk contributed {dim.contribution:.1f} points ({reason}).")
    return " ".join(lines)


def assess_clauses_batch(clauses: List[Dict[str, Any]]) -> Tuple[List[ClauseAnalysisResult], DocumentRiskAssessment]:
    """Batch clause risk assessment (Stage 2, no LLM) — the entry point that
    replaces the old per-clause analyze_clause()/score_risk_points() path.
    Batch, not per-clause, because the Hybrid Explainable Risk Engine's
    entropy-weighted dimension fusion is inherently a document-level
    statistic (see risk_engine/base.py): scoring one clause at a time can't
    produce it, since a single clause has no distribution of scores across
    the rest of the document to derive weights from.

    `clauses` items need at least 'text_content' (and 'section_name' for a
    better explanation/classification). They do NOT need a real database
    'id' — this runs in agents/orchestrator.py before clause IDs are
    assigned, so ids used internally here are batch-local positions, never
    persisted or exposed to callers.

    Clause TYPE classification (detect_clause_type) is untouched — only
    risk scoring itself moved to the new engine; entities/dependencies are
    still populated via the existing regex extractors, a separate concern
    from risk scoring that was never part of the keyword-weight system.
    """
    from agents.feature_extraction_agent import extract_legal_features_batch

    if not clauses:
        empty_doc = DocumentRiskAssessment(
            clause_assessments=[], dimension_weights={}, average_lrsi=0.0,
            document_risk_score=0.0, high_count=0, medium_count=0, low_count=0,
        )
        return [], empty_doc

    indexed_clauses = [
        {**c, "id": i, "text_content": c.get("text_content", "")}
        for i, c in enumerate(clauses)
    ]

    feature_vectors = extract_legal_features_batch(indexed_clauses)
    engine = _get_risk_engine()
    risk_inputs = [
        RiskClauseInput(clause_id=ic["id"], text=ic["text_content"], features=fv)
        for ic, fv in zip(indexed_clauses, feature_vectors)
    ]
    document_assessment = engine.score_document(risk_inputs)
    assessment_by_id = {a.clause_id: a for a in document_assessment.clause_assessments}

    results = []
    for original, ic in zip(clauses, indexed_clauses):
        combined_text = f"{original.get('section_name', 'Clause')}\n{ic['text_content']}"
        clause_type, _confidence = detect_clause_type(combined_text)
        assessment = assessment_by_id[ic["id"]]

        entities = [
            EntityRelation(source=source, relation=relation, target=target)
            for source, relation, target in extract_obligations(ic["text_content"])[:5]
        ]
        dependencies = extract_section_refs(ic["text_content"])
        top_dimension = assessment.dimension_breakdown[0].dimension if assessment.dimension_breakdown else "None"

        results.append(ClauseAnalysisResult(
            classification=clause_type,
            risk_category=top_dimension,
            risk_level=assessment.classification,
            risk_score=round(assessment.lrsi),
            confidence=round(assessment.confidence),
            dimension_breakdown=assessment.dimension_breakdown,
            explanation=_build_explanation(assessment),
            entities=entities,
            dependencies=dependencies,
        ))

    return results, document_assessment


class LLMRiskAssessment(BaseModel):
    risk_level: str = Field(description="Severity: High, Medium, Low, or None")
    risk_category: str = Field(description="Category of risk: Financial, Compliance, Operational, Legal, or None")
    risk_score: int = Field(description="Numeric risk score from 0 to 100")
    explanation: str = Field(description="Detailed explanation citing the specific language in the clause that drove this assessment")


def analyze_clause_risk_with_llm(section_name: str, text_content: str) -> LLMRiskAssessment:
    """On-demand LLM risk re-analysis for a single clause — NOT called during
    ingestion. The Hybrid Explainable Risk Engine (assess_clauses_batch,
    above) remains the fast, quota-safe default every clause gets on
    upload; this exists because even a well-tuned automatic pipeline can
    miss nuance (implicit obligations, unusual phrasing, interactions
    between sentences) that requires real legal judgment. Only invoked when
    a user explicitly requests it from the UI, one clause at a time, so it
    never reintroduces the N-calls-per-upload latency/quota problem the
    rule-based (now engine-based) rewrite was built to avoid."""
    system_instruction = (
        "You are an expert legal counsel and risk analyst. Assess the risk of the "
        "provided contract clause using your full legal judgment — not just keyword "
        "matching. Consider implicit obligations, ambiguous phrasing, and how this "
        "clause could actually play out in a dispute. Assign a risk_category "
        "(Financial, Compliance, Operational, Legal, or None), a risk_level "
        "(High, Medium, Low, or None), and a risk_score (0-100) consistent with that "
        "level. In 'explanation', cite the specific words/phrases in the clause that "
        "drove your assessment."
    )
    prompt = f"Section Heading: {section_name}\nClause Content:\n{text_content}"
    return invoke_llm_structured(system_instruction, prompt, LLMRiskAssessment)
