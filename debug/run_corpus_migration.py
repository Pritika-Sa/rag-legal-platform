"""Sprint 2D, Task 3 — corpus migration: backup -> validate -> dry-run ->
(only if clean) write. Replaces stale/legacy persisted risk data with fresh
output from the current Hybrid Explainable Risk Engine, using the exact
same functions the live orchestrator calls (agents.analyzer_agent.
assess_clauses_batch, agents.risk_scoring_agent.assess_document_risk) so
migrated documents are indistinguishable from documents freshly uploaded
today. No fusion/EWM/Gini/Jenks/alpha/semantic/feature-scoring/extraction
logic is touched by this script — it only calls existing, unmodified
entry points and persists their output via the existing
database.crud.update_clause_risk / update_document_analysis functions.
"""

import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKUP_DIR = "backups"


def backup_corpus():
    from database.crud import get_db
    db = get_db()
    ts = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs(BACKUP_DIR, exist_ok=True)

    documents = list(db.documents.find({}))
    clauses = list(db.clauses.find({}))
    for d in documents:
        d["_id"] = str(d["_id"])
    for c in clauses:
        c["_id"] = str(c["_id"])

    doc_path = os.path.join(BACKUP_DIR, f"documents_backup_{ts}.json")
    clause_path = os.path.join(BACKUP_DIR, f"clauses_backup_{ts}.json")
    with open(doc_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2, default=str)
    with open(clause_path, "w", encoding="utf-8") as f:
        json.dump(clauses, f, indent=2, default=str)

    return {
        "timestamp": ts, "doc_path": doc_path, "clause_path": clause_path,
        "n_documents": len(documents), "n_clauses": len(clauses),
        "doc_file_bytes": os.path.getsize(doc_path), "clause_file_bytes": os.path.getsize(clause_path),
    }


def validate_backup(manifest):
    from database.crud import get_db
    db = get_db()

    with open(manifest["doc_path"], "r", encoding="utf-8") as f:
        reloaded_docs = json.load(f)
    with open(manifest["clause_path"], "r", encoding="utf-8") as f:
        reloaded_clauses = json.load(f)

    live_doc_count = db.documents.count_documents({})
    live_clause_count = db.clauses.count_documents({})

    checks = {
        "doc_count_matches_live": len(reloaded_docs) == live_doc_count == manifest["n_documents"],
        "clause_count_matches_live": len(reloaded_clauses) == live_clause_count == manifest["n_clauses"],
        "doc_file_nonempty": manifest["doc_file_bytes"] > 0,
        "clause_file_nonempty": manifest["clause_file_bytes"] > 0,
        "json_roundtrip_ok": isinstance(reloaded_docs, list) and isinstance(reloaded_clauses, list),
        "every_document_has_id_and_name": all("id" in d and "name" in d for d in reloaded_docs),
        "every_clause_has_id_and_doc_id": all("id" in c and "doc_id" in c for c in reloaded_clauses),
    }
    checks["all_passed"] = all(checks.values())
    return checks


def _recompute_document(doc, clauses):
    """Runs the exact live-pipeline risk-scoring path (no DB writes) for
    one document. Returns (identified, risk_results, document_assessment,
    doc_risk) or raises."""
    from agents.analyzer_agent import assess_clauses_batch
    from agents.risk_scoring_agent import assess_document_risk

    identified = [
        {"section_name": c.get("section_name", "Clause"), "text_content": c.get("text_content", ""),
         "classification": c.get("classification")}
        for c in clauses
    ]
    risk_results, document_assessment = assess_clauses_batch(identified)

    db_clauses_for_doc_scoring = [
        {**c, "risk_level": r.risk_level, "risk_category": r.risk_category,
         "risk_score": r.risk_score, "confidence": r.confidence}
        for c, r in zip(clauses, risk_results)
    ]
    doc_risk = assess_document_risk(doc["name"], db_clauses_for_doc_scoring)
    return identified, risk_results, document_assessment, doc_risk


def run(mode: str, out_dir="debug_output"):
    """mode: 'dry_run' (compute only, no writes) or 'write' (persist)."""
    from database import crud
    from database.crud import get_db

    assert mode in ("dry_run", "write")
    db = get_db()
    docs = list(db.documents.find({}, {"_id": 0}))
    docs.sort(key=lambda d: d.get("id", 0))

    report = {"mode": mode, "documents": [], "errors": []}
    for doc in docs:
        clauses = crud.get_clauses_for_document(doc["id"])
        if not clauses:
            report["errors"].append({"doc_id": doc["id"], "name": doc["name"], "reason": "no persisted clauses"})
            continue

        had_dimension_breakdown = bool(clauses[0].get("dimension_breakdown"))
        old_explanation_sample = (clauses[0].get("explanation") or "")[:60]
        was_legacy = "base tier" in old_explanation_sample or old_explanation_sample == "Error analyzing risk"

        try:
            identified, risk_results, document_assessment, doc_risk = _recompute_document(doc, clauses)
        except Exception as e:
            report["errors"].append({
                "doc_id": doc["id"], "name": doc["name"], "reason": str(e),
                "traceback": traceback.format_exc(),
            })
            print(f"FAIL doc_id={doc['id']:>3}  {doc['name'][:40]:<40}  {e}")
            if mode == "write":
                print("Stopping migration immediately (no partial writes) due to unexpected error.")
                report["stopped_early"] = True
                break
            continue

        entry = {
            "doc_id": doc["id"], "name": doc["name"], "document_type": doc.get("document_type"),
            "n_clauses": len(clauses),
            "had_dimension_breakdown_before": had_dimension_breakdown,
            "was_legacy_or_failure_before": was_legacy,
            "score_before": doc.get("document_risk_score"),
            "level_before": doc.get("document_risk_level"),
            "score_after": doc_risk.risk_score,
            "level_after": doc_risk.risk_level,
        }
        report["documents"].append(entry)
        print(f"{'DRY' if mode=='dry_run' else 'MIGRATED'} doc_id={doc['id']:>3}  {doc['name'][:35]:<35}  "
              f"{entry['score_before']}({entry['level_before']}) -> {entry['score_after']}({entry['level_after']})  "
              f"legacy_before={was_legacy}")

        if mode == "write":
            try:
                for clause, result in zip(clauses, risk_results):
                    crud.update_clause_risk(
                        clause["id"], result.risk_level, result.risk_category, result.risk_score,
                        result.explanation, source="Sprint2D_migration",
                        confidence=result.confidence,
                        dimension_breakdown=[d.model_dump() for d in result.dimension_breakdown],
                    )
                crud.update_document_analysis(
                    doc["id"],
                    document_risk_score=doc_risk.risk_score,
                    document_risk_level=doc_risk.risk_level,
                )
                crud.add_audit_log(
                    "sprint2d_migration",
                    f"Doc {doc['id']} ('{doc['name']}') migrated to current Hybrid LRSI engine: "
                    f"{entry['score_before']}({entry['level_before']}) -> {entry['score_after']}({entry['level_after']})",
                )
            except Exception as e:
                report["errors"].append({
                    "doc_id": doc["id"], "name": doc["name"], "reason": f"write failed: {e}",
                    "traceback": traceback.format_exc(),
                })
                print(f"WRITE FAILED doc_id={doc['id']}: {e}")
                report["stopped_early"] = True
                break

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"corpus_migration_{mode}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nWrote {out_path}")
    return report


if __name__ == "__main__":
    print(backup_corpus())
