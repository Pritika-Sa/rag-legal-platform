"""Sprint 4B validation — corpus-wide before/after comparison of the
word-boundary keyword-matching fix. Read-only against MongoDB; the only
"code change" is an in-process, try/finally-scoped monkey-patch of
rule_engine.matched_keywords back to plain substring containment (i.e.
pre-Sprint-4B behavior) for the duration of one function call — same
technique used in Sprints 2C/3 to isolate a single change's effect.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _old_matched_keywords(clause_type, text_lower):
    import agents.rule_engine as re_mod
    rules = re_mod.CLAUSE_RULES[clause_type]
    return [kw for kw in rules["keywords"] if kw in text_lower]


class _patched_old:
    def __enter__(self):
        import agents.rule_engine as re_mod
        self._mod = re_mod
        self._original = re_mod.matched_keywords
        re_mod.matched_keywords = _old_matched_keywords
        return self

    def __exit__(self, *exc):
        self._mod.matched_keywords = self._original
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
    return [(o.clause_type, round(o.confidence_score, 3), o.clause_text[:80]) for o in objs]


def _total_keyword_hits(full_text):
    """Total keyword hits summed across every candidate block x every
    category -- a direct, corpus-wide measure of 'how many keyword matches
    fired', independent of which category ends up winning."""
    from agents.clause_identifier_agent import _segment_into_clause_candidates
    from agents.rule_engine import CLAUSE_RULES, matched_keywords
    blocks = _segment_into_clause_candidates(full_text)
    total = 0
    for block in blocks:
        text_lower = block.lower()
        for c_type in CLAUSE_RULES:
            total += len(matched_keywords(c_type, text_lower))
    return total


def validate_document(doc):
    full_text, page_mapping = _rebuild_full_text(doc["path"])

    with _patched_old():
        before_types = _identify(full_text, page_mapping)
        before_hits = _total_keyword_hits(full_text)

    after_types = _identify(full_text, page_mapping)
    after_hits = _total_keyword_hits(full_text)

    before_set = [(t, c) for t, c, _ in before_types]
    after_set = [(t, c) for t, c, _ in after_types]

    changed = []
    for i, ((bt, bc, btext), (at, ac, atext)) in enumerate(zip(before_types, after_types)):
        if bt != at:
            changed.append({"index": i, "text_preview": btext, "before_type": bt, "before_conf": bc,
                             "after_type": at, "after_conf": ac})

    return {
        "doc_id": doc["id"], "name": doc["name"], "document_type": doc.get("document_type"),
        "n_clauses_before": len(before_types), "n_clauses_after": len(after_types),
        "total_keyword_hits_before": before_hits, "total_keyword_hits_after": after_hits,
        "keyword_hits_removed": before_hits - after_hits,
        "n_classification_changes": len(changed),
        "classification_changes": changed,
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
                  f"keyword_hits {r['total_keyword_hits_before']}->{r['total_keyword_hits_after']} "
                  f"(removed {r['keyword_hits_removed']})  "
                  f"classification_changes={r['n_classification_changes']}")
        except Exception as e:
            errors.append({"doc_id": doc["id"], "name": doc["name"], "reason": str(e)})
            print(f"FAIL doc_id={doc['id']:>3}  {doc['name'][:35]:<35}  {e}")

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "keyword_matching_validation.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"results": results, "errors": errors}, f, indent=2, default=str)
    print(f"\nWrote {out_path}  ({len(results)} succeeded, {len(errors)} failed)")
    return results, errors


if __name__ == "__main__":
    run()
