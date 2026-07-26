"""Sprint 4C validation -- corpus-wide before/after comparison of the
taxonomy expansion (4 new categories: Recitals and Background, Term and
Duration, Workplace Monitoring and Surveillance, Leave and Time Off; 4
expanded categories: Coverage and Scope, Cancellation, Data Protection,
Counterparts).

Read-only against MongoDB; the only "code change" is an in-process,
try/finally-scoped monkey-patch of agents.rule_engine.CLAUSE_RULES /
_KEYWORD_PATTERNS back to the pre-Sprint-4C 49-category taxonomy (snapshot
in debug/_pre_4c_clause_rules_snapshot.json, taken from git HEAD before any
Sprint 4C edit) for the duration of the "before" pass only -- same
technique used in Sprints 2C/3/4B to isolate a single change's effect.
Never edits risk_engine/, rule_engine.matched_keywords's algorithm,
clause_identifier_agent.py, or parser_agent.py.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "_pre_4c_clause_rules_snapshot.json")


def _load_old_rules():
    with open(_SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_patterns(rules_dict):
    return {
        c_type: [(kw, re.compile(r"\b" + re.escape(kw) + r"\b")) for kw in rules["keywords"]]
        for c_type, rules in rules_dict.items()
    }


class _patched_old_taxonomy:
    """Swaps agents.rule_engine.CLAUSE_RULES / _KEYWORD_PATTERNS for the
    pre-Sprint-4C snapshot for the duration of the `with` block, restoring
    the live (Sprint 4C) taxonomy unconditionally afterward. The matching
    *algorithm* (word-boundary regex, Sprint 4B) is untouched -- only the
    category/keyword/regex *data* is swapped."""

    def __enter__(self):
        import agents.rule_engine as re_mod
        self._mod = re_mod
        self._orig_rules = re_mod.CLAUSE_RULES
        self._orig_patterns = re_mod._KEYWORD_PATTERNS
        old_rules = _load_old_rules()
        re_mod.CLAUSE_RULES = old_rules
        re_mod._KEYWORD_PATTERNS = _build_patterns(old_rules)
        return self

    def __exit__(self, *exc):
        self._mod.CLAUSE_RULES = self._orig_rules
        self._mod._KEYWORD_PATTERNS = self._orig_patterns
        return False


def _rebuild_full_text(source_path: str):
    from agents.parser_agent import parse_document, enforce_chunk_bounds
    raw_sections = enforce_chunk_bounds(parse_document(source_path))
    blocks = [f"{s['section_name']}\n{s['text_content']}" for s in raw_sections]
    page_mapping = [{"page_number": s.get("page_num"), "text_content": b} for s, b in zip(raw_sections, blocks)]
    return "\n\n".join(blocks), page_mapping


def _identify(full_text, page_mapping):
    from agents.clause_identifier_agent import identify_clauses
    objs = identify_clauses(full_text, page_mapping)
    return [
        {"clause_type": o.clause_type, "confidence": round(o.confidence_score, 3), "text": o.clause_text}
        for o in objs
    ]


NEW_CATEGORIES = {
    "Recitals and Background", "Term and Duration",
    "Workplace Monitoring and Surveillance", "Leave and Time Off",
}
EXPANDED_CATEGORIES = {"Coverage and Scope", "Cancellation", "Data Protection", "Counterparts"}


def _score_clause_sets(before_clauses, after_clauses):
    """Batch-scores both clause sets through the live, unmodified
    HybridExplainableRiskEngine (same call pattern as Sprint 2C's
    run_corpus_validation.py) to see how document-level LRSI moves purely
    as a function of which clauses got included -- the risk engine itself
    is never touched or patched here."""
    from agents.feature_extraction_agent import extract_legal_features_batch
    from risk_engine.schemas import ClauseInput as RiskClauseInput
    from risk_engine.hybrid_engine import HybridExplainableRiskEngine
    from services.semantic_similarity import embed_texts

    def _score(clauses):
        indexed = [{**c, "id": i, "text_content": c["text"]} for i, c in enumerate(clauses)]
        feature_vectors = extract_legal_features_batch(indexed)
        risk_inputs = [
            RiskClauseInput(clause_id=ic["id"], text=ic["text_content"], features=fv)
            for ic, fv in zip(indexed, feature_vectors)
        ]
        engine = HybridExplainableRiskEngine(embed_fn=embed_texts)
        return engine.score_document(risk_inputs) if risk_inputs else None

    before_result = _score(before_clauses)
    after_result = _score(after_clauses)
    return (
        round(before_result.document_risk_score, 2) if before_result else None,
        round(after_result.document_risk_score, 2) if after_result else None,
    )


def validate_document(doc):
    full_text, page_mapping = _rebuild_full_text(doc["path"])

    with _patched_old_taxonomy():
        before = _identify(full_text, page_mapping)

    after = _identify(full_text, page_mapping)

    # Match clauses across before/after by exact text (identify_clauses's
    # candidate segmentation is taxonomy-independent, so the same block
    # of text appears in both runs iff it cleared MIN_CONFIDENCE in that run).
    before_by_text = {c["text"]: c for c in before}
    after_by_text = {c["text"]: c for c in after}

    recovered = [c for text, c in after_by_text.items() if text not in before_by_text]
    dropped = [c for text, c in before_by_text.items() if text not in after_by_text]
    reclassified = [
        {"text": text, "before_type": before_by_text[text]["clause_type"],
         "before_conf": before_by_text[text]["confidence"],
         "after_type": after_by_text[text]["clause_type"],
         "after_conf": after_by_text[text]["confidence"]}
        for text in before_by_text.keys() & after_by_text.keys()
        if before_by_text[text]["clause_type"] != after_by_text[text]["clause_type"]
    ]

    dist_before, dist_after = {}, {}
    for c in before:
        dist_before[c["clause_type"]] = dist_before.get(c["clause_type"], 0) + 1
    for c in after:
        dist_after[c["clause_type"]] = dist_after.get(c["clause_type"], 0) + 1

    recovery_by_category = {}
    for c in recovered:
        recovery_by_category[c["clause_type"]] = recovery_by_category.get(c["clause_type"], 0) + 1

    # Regression guard: any reclassification landing on a category outside
    # the 4 new + 4 expanded ones would mean an untouched category's
    # matching behavior shifted -- should never happen since neither its
    # keywords/regex nor the matching algorithm changed.
    unexpected_regressions = [
        r for r in reclassified
        if r["after_type"] not in NEW_CATEGORIES and r["after_type"] not in EXPANDED_CATEGORIES
        and r["before_type"] not in NEW_CATEGORIES and r["before_type"] not in EXPANDED_CATEGORIES
    ]

    score_before, score_after = None, None
    if recovered or dropped or reclassified:
        try:
            score_before, score_after = _score_clause_sets(before, after)
        except Exception as e:
            score_before, score_after = f"ERROR: {e}", f"ERROR: {e}"

    return {
        "doc_id": doc["id"], "name": doc["name"], "document_type": doc.get("document_type"),
        "n_clauses_before": len(before), "n_clauses_after": len(after),
        "n_recovered": len(recovered), "n_dropped": len(dropped), "n_reclassified": len(reclassified),
        "recovered": [{"clause_type": c["clause_type"], "confidence": c["confidence"], "text": c["text"][:200]}
                      for c in recovered],
        "dropped": [{"clause_type": c["clause_type"], "confidence": c["confidence"], "text": c["text"][:200]}
                    for c in dropped],
        "reclassified": [{**r, "text": r["text"][:200]} for r in reclassified],
        "unexpected_regressions": unexpected_regressions,
        "recovery_by_category": recovery_by_category,
        "distribution_before": dist_before,
        "distribution_after": dist_after,
        "persisted_document_risk_score": doc.get("document_risk_score"),
        "document_risk_score_before_reconstructed": score_before,
        "document_risk_score_after": score_after,
        "unaffected": len(recovered) == 0 and len(dropped) == 0 and len(reclassified) == 0,
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
            tag = "UNAFFECTED" if r["unaffected"] else "CHANGED"
            print(f"OK   doc_id={doc['id']:>3}  {doc['name'][:35]:<35}  {tag:<10} "
                  f"recovered={r['n_recovered']} dropped={r['n_dropped']} reclassified={r['n_reclassified']} "
                  f"regressions={len(r['unexpected_regressions'])}  "
                  f"score {r['document_risk_score_before_reconstructed']} -> {r['document_risk_score_after']}")
        except Exception as e:
            import traceback
            errors.append({"doc_id": doc["id"], "name": doc["name"], "reason": str(e), "traceback": traceback.format_exc()})
            print(f"FAIL doc_id={doc['id']:>3}  {doc['name'][:35]:<35}  {e}")

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "taxonomy_expansion_validation.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"results": results, "errors": errors}, f, indent=2, default=str)
    print(f"\nWrote {out_path}  ({len(results)} succeeded, {len(errors)} failed)")
    return results, errors


if __name__ == "__main__":
    run()
