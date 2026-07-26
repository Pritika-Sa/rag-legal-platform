"""Sprint 1 LRSI debugging framework (read-only observability layer).

Never modifies risk_engine/fusion.py, risk_engine/thresholds.py, or
risk_engine/dimensions.py — every function here either reads data those
modules already compute (per-clause DimensionScore fields, persisted
clause/document records) or re-derives a value from an existing *pure*
function they already expose (fusion.gini_coefficient,
document_classifier.classify_document_type_ranked,
clause_identifier_agent._segment_into_clause_candidates,
rule_engine.detect_clause_type) that the live pipeline currently computes
and discards, or simply doesn't call yet. No scoring logic is added,
removed, or reweighted anywhere in this module.

Two entry points matter for callers:
  - clause_debug_record() / document_summary_record(): build the Task 1/2
    JSON-shaped records from a clause dict (either agents/orchestrator.py's
    in-flight `identified[i]` shape, or an equally-shaped row from
    database.crud.get_clauses_for_document — both use the same field
    names, so this module works identically against a live run or
    persisted history).
  - write_jsonl() / render_human_readable(): Task 5's two output formats,
    the second always generated FROM the first so they can't drift apart.
"""

import json
import os
import statistics
from typing import Any, Dict, List, Optional, Tuple

DIMENSIONS = ["Financial", "Legal", "Compliance", "Operational", "Ambiguity"]


def is_debug_enabled() -> bool:
    """Gate for the orchestrator.py hook (Task 6) — off by default so
    Sprint 1 instrumentation has zero cost/output in normal operation."""
    return os.environ.get("LRSI_DEBUG", "").strip().lower() in ("1", "true", "yes")


# --------------------------------------------------------------------------
# Task 1 — clause-level debug record
# --------------------------------------------------------------------------

def clause_debug_record(c: Dict[str, Any]) -> Dict[str, Any]:
    """One Task-1-shaped record from a clause dict shaped like
    agents/orchestrator.py's `identified[i]` after risk scoring — equally,
    a row from database.crud.get_clauses_for_document (same field names:
    id, section_name, classification, text_content, risk_score, risk_level,
    confidence, dimension_breakdown). `confidence_score` (the clause-*type*
    identification confidence, distinct from `confidence` = risk
    confidence) is only present on a live in-flight `identified[i]` dict —
    agents/database/crud.py::add_clauses_bulk's explicit field allowlist
    does not persist it, so it reads as None when this is called against
    already-persisted history. See IMPLEMENTATION_NOTES.md for the fix.
    """
    text = c.get("text_content", "") or ""
    dims = {d["dimension"]: d for d in (c.get("dimension_breakdown") or [])}

    top_prototype = None
    best_sim = -1.0
    for dim_name, d in dims.items():
        ev = d.get("semantic_evidence")
        if ev and ev.get("similarity", -1) > best_sim:
            best_sim = ev["similarity"]
            top_prototype = {"dimension": dim_name, "prototype": ev["prototype"], "similarity": ev["similarity"]}

    return {
        "clause_id": c.get("id"),
        "clause_title": c.get("section_name"),
        "clause_type": c.get("classification"),
        "type_confidence": c.get("confidence_score"),
        "char_len": len(text),
        "text_preview": text[:200],
        "dimensions": {
            d: {
                "F": dims[d]["feature_signal"],
                "E": dims[d]["semantic_signal"],
                "alpha": dims[d]["alpha"],
                "score": dims[d]["score"],
                "weight": dims[d]["weight"],
                "contribution": dims[d]["contribution"],
                "feature_evidence": dims[d]["feature_evidence"],
                "semantic_evidence": dims[d]["semantic_evidence"],
            }
            for d in DIMENSIONS if d in dims
        },
        "top_prototype_match": top_prototype,
        "lrsi": c.get("risk_score"),
        "risk_level": c.get("risk_level"),
        "risk_confidence": c.get("confidence"),
    }


# --------------------------------------------------------------------------
# Task 2 — document-level summary
# --------------------------------------------------------------------------

def document_summary_record(
    doc: Dict[str, Any],
    clause_records: List[Dict[str, Any]],
    *,
    document_type_confidence: Optional[float] = None,
    n_raw_blocks: Optional[int] = None,
    n_chunked_sections: Optional[int] = None,
    clause_thresholds: Optional[Tuple[float, float]] = None,
    document_thresholds: Optional[Tuple[float, float, float]] = None,
    threshold_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """One Task-2-shaped record. `dimension_weights`/`dimension_alphas` are
    read off the first clause's dimension_breakdown rather than recomputed
    — they are a single document-level statistic (risk_engine.fusion.
    entropy_weights runs once per document), so every clause already
    carries an identical copy; reading clause 0's copy also gives a free
    consistency check (see analysis: verify they truly are identical
    across all clauses before trusting this shortcut on a new document).
    """
    lrsi_values = [c["lrsi"] for c in clause_records if c.get("lrsi") is not None]

    dimension_weights, dimension_alphas = {}, {}
    if clause_records and clause_records[0].get("dimensions"):
        for d, vals in clause_records[0]["dimensions"].items():
            dimension_weights[d] = vals["weight"]
            dimension_alphas[d] = vals["alpha"]

    gini = None
    if len(lrsi_values) >= 2:
        from risk_engine.fusion import gini_coefficient
        gini = gini_coefficient(__import__("numpy").array(lrsi_values))

    levels = [c.get("risk_level") for c in clause_records]

    return {
        "document_name": doc.get("name"),
        "document_type": doc.get("document_type"),
        "document_type_confidence": document_type_confidence,
        "n_raw_blocks": n_raw_blocks,
        "n_identified_clauses": len(clause_records),
        "n_scored_clauses": len(lrsi_values),
        "n_chunked_sections": n_chunked_sections,
        "dimension_weights": dimension_weights,
        "dimension_alphas": dimension_alphas,
        "average_lrsi": round(statistics.mean(lrsi_values), 2) if lrsi_values else None,
        "highest_lrsi": max(lrsi_values) if lrsi_values else None,
        "lowest_lrsi": min(lrsi_values) if lrsi_values else None,
        "gini_coefficient": round(gini, 4) if gini is not None else None,
        "document_risk_score": doc.get("document_risk_score"),
        "classification": doc.get("document_risk_level"),
        "clause_thresholds_used": list(clause_thresholds) if clause_thresholds else None,
        "document_thresholds_used": list(document_thresholds) if document_thresholds else None,
        "threshold_provenance": threshold_provenance,
        "high_count": levels.count("High"),
        "medium_count": levels.count("Medium"),
        "low_count": levels.count("Low"),
    }


# --------------------------------------------------------------------------
# Task 3 — top risk contributors
# --------------------------------------------------------------------------

def top_contributors(clause_records: List[Dict[str, Any]], n: int = 10) -> List[Dict[str, Any]]:
    ranked = sorted(
        (c for c in clause_records if c.get("lrsi") is not None),
        key=lambda c: c["lrsi"], reverse=True,
    )[:n]

    out = []
    for c in ranked:
        dims = c.get("dimensions") or {}
        if not dims:
            continue
        dominant = max(dims.items(), key=lambda kv: kv[1]["contribution"])
        dom_name, dom_vals = dominant
        reason_bits = []
        if dom_vals.get("feature_evidence"):
            reason_bits.append(dom_vals["feature_evidence"][0])
        if dom_vals.get("semantic_evidence"):
            reason_bits.append(f"reads similarly to: \"{dom_vals['semantic_evidence']['prototype']}\" "
                                f"(sim={dom_vals['semantic_evidence']['similarity']:.3f})")
        out.append({
            "clause_id": c["clause_id"],
            "clause_type": c["clause_type"],
            "lrsi": c["lrsi"],
            "dominant_dimension": dom_name,
            "dominant_contribution": dom_vals["contribution"],
            "reason": "; ".join(reason_bits) or "no specific evidence surfaced",
        })
    return out


# --------------------------------------------------------------------------
# Task 4 — clause extraction funnel
# --------------------------------------------------------------------------

def analyze_extraction_funnel(full_text: str) -> Dict[str, Any]:
    """Independently re-derives the raw-block funnel and rejection reasons
    by calling identify_clauses()'s own building blocks a second time —
    _segment_into_clause_candidates, detect_clause_type, and (Sprint 3)
    _looks_like_structured_field are all already-public, pure functions;
    this never touches identify_clauses itself, so it cannot change what
    the live pipeline actually does. Blocks recovered by the Sprint 3
    structural acceptance path are reported separately from blocks that
    matched a real CLAUSE_RULES category, so recovery rate is directly
    visible rather than folded into a generic "accepted" count.
    """
    from agents.clause_identifier_agent import (
        _segment_into_clause_candidates, _looks_like_structured_field,
        MIN_BLOCK_CHARS, MIN_CONFIDENCE, STRUCTURED_FIELD_TYPE,
    )
    from agents.rule_engine import detect_clause_type

    blocks = _segment_into_clause_candidates(full_text)
    accepted, recovered, rejected = [], [], []
    seen = set()

    for block in blocks:
        if len(block) < MIN_BLOCK_CHARS:
            rejected.append({"preview": block[:120], "reason": "too_short",
                              "confidence": None, "detected_type": None})
            continue
        if block in seen:
            rejected.append({"preview": block[:120], "reason": "duplicate_raw_block",
                              "confidence": None, "detected_type": None})
            continue
        seen.add(block)

        clause_type, confidence = detect_clause_type(block)
        if clause_type == "General" or confidence < MIN_CONFIDENCE:
            failure_reason = "classified_general" if clause_type == "General" else "below_min_confidence"
            if _looks_like_structured_field(block):
                recovered.append({"preview": block[:120], "confidence": MIN_CONFIDENCE,
                                   "detected_type": STRUCTURED_FIELD_TYPE,
                                   "original_reason": failure_reason, "original_type": clause_type})
            else:
                rejected.append({"preview": block[:120], "reason": failure_reason,
                                  "confidence": confidence, "detected_type": clause_type})
        else:
            accepted.append({"preview": block[:120], "confidence": confidence, "detected_type": clause_type})

    return {
        "n_raw_blocks": len(blocks),
        "n_accepted_pre_dedup": len(accepted),
        "n_recovered_structured": len(recovered),
        "n_rejected": len(rejected),
        "recovery_rate": round(len(recovered) / (len(recovered) + len(rejected)), 4) if (recovered or rejected) else 0.0,
        "rejected": rejected,
        "accepted_pre_dedup": accepted,
        "recovered_structured": recovered,
    }


def count_chunked_sections(raw_sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Parser-level chunk-split count (Task 2's 'Number of Chunked
    Clauses', honest version — see IMPLEMENTATION_NOTES.md: this is a
    section-level count taken right after parser_agent.enforce_chunk_bounds,
    NOT a clause-level count, because chunk provenance does not currently
    survive clause_processing_node's full_text join. Sections sharing a
    parent are grouped so you can see exactly which original section got
    split into how many parts."""
    chunked = [s for s in raw_sections if s.get("chunk_index") is not None]
    by_parent: Dict[str, int] = {}
    for s in chunked:
        parent = s.get("parent_section_name", "?")
        by_parent[parent] = by_parent.get(parent, 0) + 1
    return {"n_chunked_sections": len(chunked), "n_original_sections_split": len(by_parent),
            "split_sections": by_parent}


# --------------------------------------------------------------------------
# Task 5 — output writers
# --------------------------------------------------------------------------

def write_jsonl(path: str, doc_summary: Dict[str, Any], clause_records: List[Dict[str, Any]],
                 top_contributors_list: List[Dict[str, Any]], funnel: Optional[Dict[str, Any]] = None) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"record_type": "document_summary", **doc_summary}, default=str) + "\n")
        if funnel is not None:
            f.write(json.dumps({"record_type": "extraction_funnel", **funnel}, default=str) + "\n")
        for tc in top_contributors_list:
            f.write(json.dumps({"record_type": "top_contributor", **tc}, default=str) + "\n")
        for c in clause_records:
            f.write(json.dumps({"record_type": "clause", **c}, default=str) + "\n")


def _dim_table(dims: Dict[str, Dict[str, Any]]) -> str:
    header = f"  {'Dimension':<12}{'F':>8}{'E':>8}{'alpha':>8}{'Score':>8}{'Weight':>8}{'Contrib':>10}"
    lines = [header, "  " + "-" * (len(header) - 2)]
    for d in DIMENSIONS:
        if d not in dims:
            continue
        v = dims[d]
        lines.append(f"  {d:<12}{v['F']:>8.3f}{v['E']:>8.3f}{v['alpha']:>8.3f}"
                      f"{v['score']:>8.3f}{v['weight']:>8.3f}{v['contribution']:>10.2f}")
    return "\n".join(lines)


def render_human_readable(jsonl_path: str, out_path: Optional[str] = None) -> str:
    """Renders the human-readable report FROM the JSONL file (never
    logged independently), so the two views can't drift apart."""
    doc_summary, funnel, contributors, clauses = None, None, [], []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            rt = rec.pop("record_type")
            if rt == "document_summary":
                doc_summary = rec
            elif rt == "extraction_funnel":
                funnel = rec
            elif rt == "top_contributor":
                contributors.append(rec)
            elif rt == "clause":
                clauses.append(rec)

    out = []
    sep = "=" * 72
    out.append(sep)
    out.append(f"DOCUMENT: {doc_summary['document_name']}")
    out.append(sep)
    out.append(f"Type: {doc_summary['document_type']} "
               f"(confidence={doc_summary['document_type_confidence']})")
    out.append(f"Raw blocks: {doc_summary['n_raw_blocks']}   "
               f"Identified: {doc_summary['n_identified_clauses']}   "
               f"Scored: {doc_summary['n_scored_clauses']}   "
               f"Chunked sections: {doc_summary['n_chunked_sections']}")
    out.append("")
    out.append("Dimension Weights:")
    for d in DIMENSIONS:
        w = doc_summary["dimension_weights"].get(d)
        a = doc_summary["dimension_alphas"].get(d)
        if w is not None:
            out.append(f"  {d:<12} weight={w:.4f}   alpha={a:.4f}")
    out.append("")
    out.append(f"Average LRSI: {doc_summary['average_lrsi']}   "
               f"Highest: {doc_summary['highest_lrsi']}   Lowest: {doc_summary['lowest_lrsi']}")
    out.append(f"Gini coefficient: {doc_summary['gini_coefficient']}")
    out.append(f"Final Document Risk Score: {doc_summary['document_risk_score']} "
               f"({doc_summary['classification']})")
    out.append(f"Clause thresholds used: {doc_summary['clause_thresholds_used']}")
    out.append(f"Document thresholds used: {doc_summary['document_thresholds_used']}")
    out.append(f"High/Medium/Low: {doc_summary['high_count']}/{doc_summary['medium_count']}/{doc_summary['low_count']}")
    out.append(sep)

    if funnel:
        out.append("")
        out.append("EXTRACTION FUNNEL")
        out.append(sep)
        out.append(f"Raw blocks: {funnel['n_raw_blocks']}  ->  "
                   f"Accepted (CLAUSE_RULES, pre-dedup): {funnel['n_accepted_pre_dedup']}  ->  "
                   f"Recovered (structured field): {funnel.get('n_recovered_structured', 0)}  ->  "
                   f"Rejected: {funnel['n_rejected']}  "
                   f"(recovery_rate={funnel.get('recovery_rate', 0.0):.2%})")
        for r in funnel.get("recovered_structured", []):
            out.append(f"  RECOVERED [was {r['original_reason']}, orig_type={r['original_type']}]: {r['preview']!r}")
        for r in funnel["rejected"]:
            out.append(f"  REJECTED [{r['reason']}] conf={r['confidence']} type={r['detected_type']}: {r['preview']!r}")
        out.append(sep)

    if contributors:
        out.append("")
        out.append("TOP RISK CONTRIBUTORS")
        out.append(sep)
        for i, tc in enumerate(contributors, 1):
            out.append(f"{i}. Clause #{tc['clause_id']} [{tc['clause_type']}]  LRSI={tc['lrsi']}  "
                       f"dominant={tc['dominant_dimension']} ({tc['dominant_contribution']:.2f} pts)")
            out.append(f"   reason: {tc['reason']}")
        out.append(sep)

    out.append("")
    out.append("PER-CLAUSE DETAIL")
    for c in clauses:
        out.append(sep)
        out.append(f"CLAUSE #{c['clause_id']}  —  \"{c['clause_title']}\"")
        out.append(f"Type: {c['clause_type']} (type_confidence={c['type_confidence']})   "
                   f"Length: {c['char_len']} chars")
        out.append(f"Preview: {c['text_preview']}")
        out.append("")
        out.append(_dim_table(c["dimensions"]))
        if c.get("top_prototype_match"):
            tp = c["top_prototype_match"]
            out.append(f"\n  Top prototype match [{tp['dimension']}]: \"{tp['prototype']}\" (sim={tp['similarity']:.3f})")
        out.append(f"\n  -> LRSI={c['lrsi']}  Risk Level={c['risk_level']}  Risk Confidence={c['risk_confidence']}")
    out.append(sep)

    text = "\n".join(out)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
    return text
