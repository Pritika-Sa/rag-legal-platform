"""Sprint 3, Task 5 — corpus-wide regression validation of the Issue 2
structural acceptance path. VALIDATION ONLY: read-only against MongoDB
(never writes), and the only "code change" is an in-process, try/finally-
scoped monkey-patch of _looks_like_structured_field back to "always False"
(i.e. pre-Sprint-3 behavior) for the duration of one function call — same
technique used in Sprint 2C to isolate the Ambiguity fix's effect.
"""

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _patched_off:
    """Forces _looks_like_structured_field to return False for the
    duration of the `with` block -- reconstructs pre-Sprint-3 clause
    identification behavior without touching any file."""

    def __enter__(self):
        import agents.clause_identifier_agent as cia
        self._cia = cia
        self._original = cia._looks_like_structured_field
        cia._looks_like_structured_field = lambda block: False
        return self

    def __exit__(self, *exc):
        self._cia._looks_like_structured_field = self._original
        return False


def _rebuild_full_text(source_path: str):
    from agents.parser_agent import parse_document, enforce_chunk_bounds
    raw_sections = enforce_chunk_bounds(parse_document(source_path))
    blocks = [f"{s['section_name']}\n{s['text_content']}" for s in raw_sections]
    page_mapping = [{"page_number": s.get("page_num"), "text_content": b} for s, b in zip(raw_sections, blocks)]
    return "\n\n".join(blocks), page_mapping


def _run_full_pipeline(full_text, page_mapping):
    """identify_clauses -> assess_clauses_batch -> assess_document_risk,
    exactly the live orchestrator path, no DB writes."""
    from agents.clause_identifier_agent import identify_clauses
    from agents.analyzer_agent import assess_clauses_batch
    from agents.risk_scoring_agent import assess_document_risk

    identified_objects = identify_clauses(full_text, page_mapping)
    identified = [
        {"section_name": obj.clause_title, "text_content": obj.clause_text,
         "classification": obj.clause_type, "confidence_score": obj.confidence_score,
         "page_num": obj.page_number}
        for obj in identified_objects
    ]
    risk_results, document_assessment = assess_clauses_batch(identified)
    db_clauses = [
        {**c, "risk_level": r.risk_level, "risk_category": r.risk_category,
         "risk_score": r.risk_score, "confidence": r.confidence}
        for c, r in zip(identified, risk_results)
    ]
    doc_risk = assess_document_risk("regression_check", db_clauses)
    return identified, risk_results, doc_risk


def validate_document(doc):
    full_text, page_mapping = _rebuild_full_text(doc["path"])

    with _patched_off():
        before_identified, before_results, before_doc_risk = _run_full_pipeline(full_text, page_mapping)

    after_identified, after_results, after_doc_risk = _run_full_pipeline(full_text, page_mapping)

    before_types = {}
    for c in before_identified:
        before_types[c["classification"]] = before_types.get(c["classification"], 0) + 1
    after_types = {}
    for c in after_identified:
        after_types[c["classification"]] = after_types.get(c["classification"], 0) + 1

    n_structured_field = after_types.get("Structured Field", 0)

    return {
        "doc_id": doc["id"], "name": doc["name"], "document_type": doc.get("document_type"),
        "n_clauses_before": len(before_identified),
        "n_clauses_after": len(after_identified),
        "n_recovered_clauses": len(after_identified) - len(before_identified),
        "n_structured_field_clauses": n_structured_field,
        "clause_types_before": before_types,
        "clause_types_after": after_types,
        "persisted_document_risk_score": doc.get("document_risk_score"),
        "persisted_document_risk_level": doc.get("document_risk_level"),
        "reconstructed_score_before": before_doc_risk.risk_score,
        "reconstructed_level_before": before_doc_risk.risk_level,
        "score_after": after_doc_risk.risk_score,
        "level_after": after_doc_risk.risk_level,
        "score_delta": after_doc_risk.risk_score - before_doc_risk.risk_score,
    }


def run(out_dir="debug_output"):
    from database.crud import get_db
    db = get_db()
    docs = list(db.documents.find({}, {"_id": 0}))
    docs.sort(key=lambda d: d.get("id", 0))

    results, errors = [], []
    for doc in docs:
        try:
            r = validate_document(doc)
            results.append(r)
            print(f"OK   doc_id={doc['id']:>3}  {doc['name'][:35]:<35}  "
                  f"clauses {r['n_clauses_before']}->{r['n_clauses_after']} "
                  f"(+{r['n_recovered_clauses']}, {r['n_structured_field_clauses']} structured)  "
                  f"score {r['reconstructed_score_before']}->{r['score_after']} "
                  f"(Δ{r['score_delta']:+d})  persisted={r['persisted_document_risk_score']}")
        except Exception as e:
            errors.append({"doc_id": doc["id"], "name": doc["name"], "reason": str(e),
                            "traceback": traceback.format_exc()})
            print(f"FAIL doc_id={doc['id']:>3}  {doc['name'][:35]:<35}  {e}")

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "clause_extraction_regression.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"results": results, "errors": errors}, f, indent=2, default=str)
    print(f"\nWrote {out_path}  ({len(results)} succeeded, {len(errors)} failed)")
    return results, errors


if __name__ == "__main__":
    run()
