"""Sprint 2C — corpus-wide validation of the Sprint 2B Ambiguity fix.

VALIDATION ONLY. Never edits risk_engine/, agents/feature_extraction_agent.py,
agents/clause_identifier_agent.py, or agents/parser_agent.py. The only
"code change" in this file is a runtime, in-process monkey-patch of
risk_engine.dimensions._ambiguity_feature_signal back to its pre-Sprint-2B
form, applied for the duration of one function call and reverted immediately
after — used solely to reconstruct "before" Feature-only/Semantic-only
scores that were never persisted anywhere (Mongo only ever stored the fused
Dynamic score). "Dynamic Before" and "Risk Classification Before" instead
use the real, persisted, already-live production values — no reconstruction
needed for those.

Read-only against MongoDB throughout: never writes documents/clauses back.
"""

import json
import os
import statistics
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DIMENSIONS = ["Financial", "Legal", "Compliance", "Operational", "Ambiguity"]


def _old_ambiguity_feature_signal(fv):
    """Verbatim pre-Sprint-2B implementation of
    risk_engine.dimensions._ambiguity_feature_signal, kept here only for
    A/B reconstruction. Not used anywhere except inside _patched()."""
    from risk_engine.dimensions import WEAK_MODALS
    modals = [o.modal.lower() for o in fv.obligations if o.modal]
    if not modals:
        return 0.5
    weak = sum(1 for m in modals if m in WEAK_MODALS)
    return weak / len(modals)


class _patched:
    """Context manager: swaps risk_engine.dimensions._ambiguity_feature_signal
    for the old implementation for the duration of the `with` block only,
    then restores the current (Sprint 2B) implementation unconditionally
    (even on exception) via try/finally."""

    def __enter__(self):
        import risk_engine.dimensions as dims
        self._dims = dims
        self._original = dims._ambiguity_feature_signal
        dims._ambiguity_feature_signal = _old_ambiguity_feature_signal
        return self

    def __exit__(self, *exc):
        self._dims._ambiguity_feature_signal = self._original
        return False


def _score(risk_inputs, alpha_override):
    from risk_engine.hybrid_engine import HybridExplainableRiskEngine
    from services.semantic_similarity import embed_texts
    engine = HybridExplainableRiskEngine(embed_fn=embed_texts, alpha=alpha_override)
    return engine.score_document(risk_inputs)


def validate_document(doc, clauses, document_thresholds):
    from agents.feature_extraction_agent import extract_legal_features_batch
    from risk_engine.schemas import ClauseInput as RiskClauseInput
    from risk_engine import fusion

    indexed = [{**c, "id": i, "text_content": c.get("text_content", "")} for i, c in enumerate(clauses)]
    feature_vectors = extract_legal_features_batch(indexed)  # has_prose_verb populated by current code either way
    risk_inputs = [
        RiskClauseInput(clause_id=ic["id"], text=ic["text_content"], features=fv)
        for ic, fv in zip(indexed, feature_vectors)
    ]

    with _patched():
        old_feature = _score(risk_inputs, {d: 1.0 for d in DIMENSIONS})
        old_semantic = _score(risk_inputs, {d: 0.0 for d in DIMENSIONS})
        old_dynamic = _score(risk_inputs, None)

    new_feature = _score(risk_inputs, {d: 1.0 for d in DIMENSIONS})
    new_semantic = _score(risk_inputs, {d: 0.0 for d in DIMENSIONS})
    new_dynamic = _score(risk_inputs, None)

    n_structured = sum(1 for fv in feature_vectors if fv.has_prose_verb is False)
    n_prose = sum(1 for fv in feature_vectors if fv.has_prose_verb is True)

    ambiguity_f = []
    ambiguity_contrib = []
    ambiguity_weight = None
    top_ambiguity = []
    for a in new_dynamic.clause_assessments:
        amb = next((d for d in a.dimension_breakdown if d.dimension == "Ambiguity"), None)
        if amb is None:
            continue
        ambiguity_f.append(amb.feature_signal)
        ambiguity_contrib.append(amb.contribution)
        ambiguity_weight = amb.weight
        top_ambiguity.append((a.clause_id, amb.contribution, amb.feature_signal))
    top_ambiguity.sort(key=lambda t: t[1], reverse=True)

    old_low, old_med, old_high = document_thresholds
    new_class = fusion.classify_4tier(new_dynamic.document_risk_score, *document_thresholds)
    old_dynamic_class = fusion.classify_4tier(old_dynamic.document_risk_score, *document_thresholds)

    per_clause_old = {a.clause_id: a.lrsi for a in old_dynamic.clause_assessments}
    per_clause_new = {a.clause_id: a.lrsi for a in new_dynamic.clause_assessments}
    per_clause_delta = {cid: per_clause_new[cid] - per_clause_old[cid] for cid in per_clause_new}

    return {
        "doc_id": doc["id"], "name": doc["name"], "document_type": doc.get("document_type"),
        "n_clauses": len(clauses),
        "persisted_document_risk_score": doc.get("document_risk_score"),
        "persisted_document_risk_level": doc.get("document_risk_level"),

        "feature_only_before": round(old_feature.document_risk_score, 2),
        "feature_only_after": round(new_feature.document_risk_score, 2),
        "semantic_only_before": round(old_semantic.document_risk_score, 2),
        "semantic_only_after": round(new_semantic.document_risk_score, 2),
        "dynamic_before_persisted": doc.get("document_risk_score"),
        "dynamic_before_reconstructed": round(old_dynamic.document_risk_score, 2),
        "dynamic_after": round(new_dynamic.document_risk_score, 2),
        "classification_before_persisted": doc.get("document_risk_level"),
        "classification_before_reconstructed": old_dynamic_class,
        "classification_after": new_class,

        "avg_ambiguity_feature_signal": round(statistics.mean(ambiguity_f), 4) if ambiguity_f else None,
        "avg_ambiguity_contribution": round(statistics.mean(ambiguity_contrib), 2) if ambiguity_contrib else None,
        "ambiguity_dimension_weight": round(ambiguity_weight, 4) if ambiguity_weight is not None else None,
        "old_ambiguity_dimension_weight": round(
            next((d.weight for a in old_dynamic.clause_assessments for d in a.dimension_breakdown
                  if d.dimension == "Ambiguity"), 0.0), 4),
        "top_ambiguity_clauses": top_ambiguity[:5],
        "n_structured_clauses": n_structured,
        "n_prose_clauses": n_prose,
        "n_unknown_prose": len(feature_vectors) - n_structured - n_prose,

        "per_clause_lrsi_delta": per_clause_delta,
        "max_clause_increase": max(per_clause_delta.values()) if per_clause_delta else 0.0,
        "max_clause_decrease": min(per_clause_delta.values()) if per_clause_delta else 0.0,
    }


def run_corpus_validation(out_dir="debug_output"):
    from database import crud
    from database.crud import get_db
    from agents.analyzer_agent import _get_threshold_registry

    db = get_db()
    docs = list(db.documents.find({}, {"_id": 0}))
    docs.sort(key=lambda d: d.get("id", 0))

    registry = _get_threshold_registry()
    document_thresholds = registry.document_thresholds().cuts

    results, errors = [], []
    for doc in docs:
        clauses = crud.get_clauses_for_document(doc["id"])
        if not clauses:
            errors.append({"doc_id": doc["id"], "name": doc["name"], "reason": "no persisted clauses"})
            continue
        try:
            r = validate_document(doc, clauses, document_thresholds)
            results.append(r)
            print(f"OK   doc_id={doc['id']:>3}  {doc['name'][:40]:<40}  "
                  f"dyn {r['dynamic_before_persisted']} -> {r['dynamic_after']}")
        except Exception as e:
            tb = traceback.format_exc()
            errors.append({"doc_id": doc["id"], "name": doc["name"], "reason": str(e), "traceback": tb})
            print(f"FAIL doc_id={doc['id']:>3}  {doc['name'][:40]:<40}  {e}")

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "corpus_validation.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"results": results, "errors": errors, "document_thresholds": list(document_thresholds)},
                   f, indent=2, default=str)
    print(f"\nWrote {out_path}  ({len(results)} succeeded, {len(errors)} failed)")
    return results, errors


if __name__ == "__main__":
    run_corpus_validation()
