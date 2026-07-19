"""Per-dimension signal computation — the direct replacement for
agents/rule_engine.RISK_PHRASE_POINTS. Every dimension gets two independent
signals per clause:

  F_d (feature signal): a corpus-relative statistic derived from the
  clause's LegalFeatureVector — never a fixed point value. The same raw
  obligation count means something different in a 4-clause NDA than in a
  60-clause master services agreement, so raw quantities are converted to
  percentile rank *within this document's own clauses* (see
  _percentile_normalize) rather than compared against a hard-coded
  threshold.

  E_d (semantic signal): similarity between the clause's embedding and a
  set of natural-language dimension prototypes (risk_engine/prototypes.json)
  — see prototype_store.py. Ambiguity has no crisp prototype sentence the
  way "unlimited financial exposure" does, so its semantic signal is an
  embedding-space outlier score instead (see ambiguity_outlier_signal).

Both signals are always in [0,1]; fusion.fuse_signal combines them per
dimension without either branch ever assigning a manual point value.
"""

import math
from typing import Dict, List

import numpy as np
from scipy.stats import rankdata

from risk_engine.schemas import LegalFeatureVector, Polarity

DIMENSIONS = ["Financial", "Legal", "Compliance", "Operational", "Ambiguity"]

# Dimensions whose E_d comes from prototype-sentence similarity (see
# prototype_store.PrototypeStore). Ambiguity is deliberately excluded —
# see ambiguity_outlier_signal.
PROTOTYPE_DIMENSIONS = ["Financial", "Legal", "Compliance", "Operational"]

# Closed grammatical class used only to classify obligation polarity and
# grammatical hedging — a linguistic category, not a risk-weight lexicon.
STRONG_MODALS = {"shall", "must", "will"}
WEAK_MODALS = {"may", "might", "could", "should"}

# Taxonomy contract for agents/feature_extraction_agent.py (phase 2): its
# LegalAction.action_type / Entity.entity_type values must be drawn from
# these sets for the corresponding dimension to pick them up. Adding a new
# action/entity type here changes what gets *counted*, never how many
# points it is worth — magnitude is decided entirely by percentile rank
# and the entropy-weighted fusion downstream, not by this membership list.
LEGAL_ACTION_TYPES = {"termination", "indemnification", "waiver", "assignment", "limitation_of_liability"}
COMPLIANCE_ACTION_TYPES = {"compliance", "regulatory_filing", "sanctions", "anti_corruption"}
REGULATORY_ENTITY_TYPES = {"LAW", "ORG_REGULATOR", "STATUTE", "GPE"}


def _financial_raw(fv: LegalFeatureVector) -> float:
    """Log-scaled largest monetary figure found in the clause. Whether
    that figure is capped or uncapped is deliberately *not* folded in here
    as a multiplier — an earlier version boosted uncapped amounts by a
    flat, hand-picked 1.3x, exactly the kind of unjustified constant this
    engine exists to avoid. "Uncapped" is qualitative, open-ended language
    ("without limit", "no maximum", ...), which is precisely what the
    semantic branch (E_financial — cosine similarity to the "unlimited or
    uncapped financial exposure" prototype in prototypes.json) is built to
    catch; encoding the same signal a second time here would be double-
    counting it through one branch instead of representing it once through
    the branch suited to it. is_capped is not discarded — it still surfaces
    in feature_evidence() below, so it stays visible in the explainability
    breakdown even though it no longer independently changes the score."""
    amounts = [ft.amount for ft in fv.financial_terms if ft.amount and not ft.is_percentage]
    magnitude = max(amounts) if amounts else 0.0
    return math.log1p(magnitude)


def _legal_raw(fv: LegalFeatureVector) -> float:
    action_strength = sum(a.confidence for a in fv.legal_actions if a.action_type in LEGAL_ACTION_TYPES)
    obligation_strength = sum(
        o.confidence for o in fv.obligations if o.polarity in (Polarity.OBLIGATION, Polarity.PROHIBITION)
    )
    return action_strength + obligation_strength


def _compliance_raw(fv: LegalFeatureVector) -> float:
    regulatory_entities = sum(e.confidence for e in fv.entities if e.entity_type in REGULATORY_ENTITY_TYPES)
    compliance_actions = sum(a.confidence for a in fv.legal_actions if a.action_type in COMPLIANCE_ACTION_TYPES)
    jurisdiction_present = 1.0 if fv.jurisdiction else 0.0
    return regulatory_entities + compliance_actions + jurisdiction_present


def _operational_raw(fv: LegalFeatureVector) -> float:
    return float(len(fv.deadlines) + len(fv.dependencies))


def _ambiguity_feature_signal(fv: LegalFeatureVector) -> float:
    """Ratio of weak/hedging modals to all detected modals — already
    bounded in [0,1], so unlike the other four dimensions this is not
    corpus-percentile-normalized. A clause with no detected obligation
    language at all defaults to 0.5 (genuinely ambiguous: there is nothing
    to say it is precisely drafted)."""
    modals = [o.modal.lower() for o in fv.obligations if o.modal]
    if not modals:
        return 0.5
    weak = sum(1 for m in modals if m in WEAK_MODALS)
    return weak / len(modals)


_RAW_EXTRACTORS = {
    "Financial": _financial_raw,
    "Legal": _legal_raw,
    "Compliance": _compliance_raw,
    "Operational": _operational_raw,
}


def _percentile_normalize(values: List[float]) -> List[float]:
    n = len(values)
    if n <= 1:
        return [0.5] * n
    if max(values) == min(values):
        return [0.5] * n
    ranks = rankdata(values, method="average")
    return [float((r - 1) / (n - 1)) for r in ranks]


def compute_feature_signals(feature_vectors: List[LegalFeatureVector]) -> Dict[str, List[float]]:
    """Batch F_d computation. Returns {dimension: [F_d per clause]}, aligned
    by index with `feature_vectors`."""
    signals: Dict[str, List[float]] = {}
    for dimension, extractor in _RAW_EXTRACTORS.items():
        raw = [extractor(fv) for fv in feature_vectors]
        signals[dimension] = _percentile_normalize(raw)
    signals["Ambiguity"] = [_ambiguity_feature_signal(fv) for fv in feature_vectors]
    return signals


def feature_evidence(fv: LegalFeatureVector, dimension: str) -> List[str]:
    """Human-readable strings naming the specific extracted features that
    drove F_d for this clause/dimension — the 'which legal features were
    detected' half of the explainability contract."""
    if dimension == "Financial":
        return [
            f"financial_term: {ft.currency or ''}{ft.amount:,.0f}"
            f"{'%' if ft.is_percentage else ''}{', uncapped' if ft.is_capped is False else ''}"
            for ft in fv.financial_terms if ft.amount
        ]
    if dimension == "Legal":
        return (
            [f"legal_action: {a.action_type} (confidence {a.confidence:.2f})"
             for a in fv.legal_actions if a.action_type in LEGAL_ACTION_TYPES]
            + [f"obligation: '{o.subject} {o.modal} {o.action}' (polarity={o.polarity.value})"
               for o in fv.obligations if o.polarity in (Polarity.OBLIGATION, Polarity.PROHIBITION)]
        )
    if dimension == "Compliance":
        evidence = [f"entity: {e.text} ({e.entity_type})" for e in fv.entities if e.entity_type in REGULATORY_ENTITY_TYPES]
        evidence += [f"legal_action: {a.action_type}" for a in fv.legal_actions if a.action_type in COMPLIANCE_ACTION_TYPES]
        if fv.jurisdiction:
            evidence.append(f"jurisdiction: {fv.jurisdiction}")
        return evidence
    if dimension == "Operational":
        return (
            [f"deadline: {d.kind} = {d.value}" for d in fv.deadlines]
            + [f"dependency: {dep.relation} -> clause {dep.target_clause_id}" for dep in fv.dependencies]
        )
    if dimension == "Ambiguity":
        weak_modals = [o.modal for o in fv.obligations if o.modal and o.modal.lower() in WEAK_MODALS]
        return [f"weak modal: '{m}'" for m in weak_modals]
    return []


def ambiguity_outlier_signal(clause_embeddings: np.ndarray) -> List[float]:
    """E_ambiguity per clause: 1 - cosine similarity to the document's mean
    clause embedding. A clause that reads very differently in meaning from
    the rest of the document is a weak but real non-standardness signal —
    the semantic-branch counterpart to the grammatical modal-ratio feature
    signal above, used in place of prototype similarity for this one
    dimension (see module docstring)."""
    n = clause_embeddings.shape[0]
    if n < 2:
        return [0.5] * n
    from services.semantic_similarity import cosine_similarity_matrix
    centroid = clause_embeddings.mean(axis=0, keepdims=True)
    sims = cosine_similarity_matrix(clause_embeddings, centroid)[:, 0]
    return [float(1.0 - s) for s in sims]
