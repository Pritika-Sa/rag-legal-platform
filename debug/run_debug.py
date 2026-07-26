"""Sprint 1 debug CLI — runs the debugging framework against an already-
processed document, read-only. Does not re-run the orchestrator and does
not write anything to MongoDB; it only reads persisted clauses/document
fields and re-derives values via pure functions (see
debug/lrsi_debug_logger.py's module docstring for exactly which).

Usage:
    python -m debug.run_debug --doc-id 20 --source "uploads/4/471051998_1.pdf"
    python -m debug.run_debug --doc-id 20 --source "uploads/4/471051998_1.pdf" --alpha-ablation
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DIMENSIONS = ["Financial", "Legal", "Compliance", "Operational", "Ambiguity"]


def _rebuild_full_text(source_path: str):
    """Reconstructs the same full_text agents/orchestrator.py's
    clause_processing_node builds, so analyze_extraction_funnel() sees
    exactly what the live pipeline saw."""
    from agents.parser_agent import parse_document, enforce_chunk_bounds
    raw_sections = enforce_chunk_bounds(parse_document(source_path))
    blocks = [f"{s['section_name']}\n{s['text_content']}" for s in raw_sections]
    return "\n\n".join(blocks), raw_sections


def run_from_persisted(doc_id: int, source_path: str = None, out_dir: str = "debug_output") -> str:
    from database import crud
    from debug import lrsi_debug_logger as dbg
    from services.document_classifier import classify_document_type_ranked

    doc = crud.get_document_by_id(doc_id)
    if not doc:
        raise SystemExit(f"No document with id={doc_id}")
    clauses = crud.get_clauses_for_document(doc_id)
    if not clauses:
        raise SystemExit(f"No clauses persisted for doc_id={doc_id}")

    clause_records = [dbg.clause_debug_record(c) for c in clauses]

    funnel, chunk_info, type_conf, full_text = None, None, None, None
    if source_path:
        full_text, raw_sections = _rebuild_full_text(source_path)
        funnel = dbg.analyze_extraction_funnel(full_text)
        chunk_info = dbg.count_chunked_sections(raw_sections)
        type_conf = classify_document_type_ranked(full_text).confidence

    threshold_registry = None
    try:
        from agents.analyzer_agent import _get_threshold_registry
        threshold_registry = _get_threshold_registry()
    except Exception as e:
        print(f"  (threshold registry unavailable: {e})")

    doc_summary = dbg.document_summary_record(
        doc, clause_records,
        document_type_confidence=type_conf if type_conf is not None
            else doc.get("authenticity_document_type_confidence"),
        n_raw_blocks=funnel["n_raw_blocks"] if funnel else None,
        n_chunked_sections=chunk_info["n_chunked_sections"] if chunk_info else None,
        clause_thresholds=threshold_registry.clause_thresholds().cuts if threshold_registry else None,
        document_thresholds=threshold_registry.document_thresholds().cuts if threshold_registry else None,
        threshold_provenance={
            "clause_is_data_derived": threshold_registry.clause_thresholds().is_data_derived,
            "clause_sample_size": threshold_registry.clause_thresholds().sample_size,
            "document_is_data_derived": threshold_registry.document_thresholds().is_data_derived,
            "document_sample_size": threshold_registry.document_thresholds().sample_size,
        } if threshold_registry else None,
    )
    if chunk_info:
        doc_summary["chunk_split_sections"] = chunk_info["split_sections"]

    contributors = dbg.top_contributors(clause_records, n=10)

    os.makedirs(out_dir, exist_ok=True)
    jsonl_path = os.path.join(out_dir, f"doc_{doc_id}.jsonl")
    report_path = os.path.join(out_dir, f"doc_{doc_id}_report.txt")
    dbg.write_jsonl(jsonl_path, doc_summary, clause_records, contributors, funnel)
    dbg.render_human_readable(jsonl_path, out_path=report_path)

    print(f"Wrote {jsonl_path}")
    print(f"Wrote {report_path}")
    return jsonl_path


def run_alpha_ablation(doc_id: int, out_dir: str = "debug_output") -> str:
    """Holds clause boundaries fixed (uses the already-persisted clause
    texts) and re-scores under three alpha regimes: feature-only (alpha=1
    for every dimension), semantic-only (alpha=0), and the current dynamic
    alpha (alpha=None -> fusion.dynamic_alpha per dimension). This isolates
    which branch drives the score without touching fusion.py/dimensions.py
    — HybridExplainableRiskEngine's `alpha` override dict is already public
    API for exactly this (see risk_engine/hybrid_engine.py).
    """
    import numpy as np
    from database import crud
    from agents.feature_extraction_agent import extract_legal_features_batch
    from risk_engine.hybrid_engine import HybridExplainableRiskEngine
    from risk_engine.schemas import ClauseInput as RiskClauseInput
    from services.semantic_similarity import embed_texts

    clauses = crud.get_clauses_for_document(doc_id)
    if not clauses:
        raise SystemExit(f"No clauses persisted for doc_id={doc_id}")

    indexed = [{**c, "id": i, "text_content": c.get("text_content", "")} for i, c in enumerate(clauses)]
    feature_vectors = extract_legal_features_batch(indexed)
    risk_inputs = [
        RiskClauseInput(clause_id=ic["id"], text=ic["text_content"], features=fv)
        for ic, fv in zip(indexed, feature_vectors)
    ]

    experiments = {
        "A_feature_only": {d: 1.0 for d in DIMENSIONS},
        "B_semantic_only": {d: 0.0 for d in DIMENSIONS},
        "C_current_dynamic": None,
    }

    results = {}
    for label, alpha_override in experiments.items():
        engine = HybridExplainableRiskEngine(embed_fn=embed_texts, alpha=alpha_override)
        assessment = engine.score_document(risk_inputs)
        lrsi_values = [a.lrsi for a in assessment.clause_assessments]
        results[label] = {
            "document_risk_score": assessment.document_risk_score,
            "average_lrsi": assessment.average_lrsi,
            "dimension_weights": assessment.dimension_weights,
            "high_count": assessment.high_count, "medium_count": assessment.medium_count,
            "low_count": assessment.low_count,
            "per_clause_lrsi": {a.clause_id: a.lrsi for a in assessment.clause_assessments},
        }

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"doc_{doc_id}_alpha_ablation.txt")
    lines = ["=" * 72, f"ALPHA ABLATION — doc_id={doc_id}", "=" * 72]
    for label, r in results.items():
        lines.append(f"\n[{label}]")
        lines.append(f"  document_risk_score = {r['document_risk_score']}")
        lines.append(f"  average_lrsi         = {r['average_lrsi']}")
        lines.append(f"  High/Medium/Low      = {r['high_count']}/{r['medium_count']}/{r['low_count']}")
        lines.append(f"  dimension_weights    = { {k: round(v,4) for k,v in r['dimension_weights'].items()} }")
    lines.append("\nPER-CLAUSE LRSI ACROSS EXPERIMENTS")
    lines.append(f"{'clause_id':>10} {'A_feature':>12} {'B_semantic':>12} {'C_current':>12}")
    for cid in results["C_current_dynamic"]["per_clause_lrsi"]:
        a = results["A_feature_only"]["per_clause_lrsi"].get(cid)
        b = results["B_semantic_only"]["per_clause_lrsi"].get(cid)
        c = results["C_current_dynamic"]["per_clause_lrsi"].get(cid)
        lines.append(f"{cid:>10} {a:>12.2f} {b:>12.2f} {c:>12.2f}")

    text = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {path}")
    print(text)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc-id", type=int, required=True)
    parser.add_argument("--source", type=str, default=None)
    parser.add_argument("--alpha-ablation", action="store_true")
    args = parser.parse_args()

    run_from_persisted(args.doc_id, args.source)
    if args.alpha_ablation:
        run_alpha_ablation(args.doc_id)
