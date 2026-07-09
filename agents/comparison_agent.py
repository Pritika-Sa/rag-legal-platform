import difflib
from collections import Counter
from pydantic import BaseModel, Field
from typing import List, Dict, Any

UNCHANGED_THRESHOLD = 0.97
MODIFIED_THRESHOLD = 0.55


class ComparisonResult(BaseModel):
    similarity_score: int = Field(description="Similarity score between the two documents from 0 to 100")
    change_summary: str = Field(description="A high-level summary of the major differences")
    added_clauses: List[str] = Field(description="Clauses added in Document B not in Document A")
    removed_clauses: List[str] = Field(description="Clauses removed from Document B that were in Document A")
    modified_clauses: List[str] = Field(description="Clauses that exist in both but were materially modified")
    risk_changes: str = Field(description="Analysis of how modifications impact the risk profile")
    difference_report: str = Field(description="Detailed difference report of textual and semantic variations")


def _risk_distribution(clauses: List[Dict[str, Any]]) -> Counter:
    return Counter(c.get("risk_level", "None") for c in clauses)


def compare_documents(clauses_a: List[Dict[str, Any]], clauses_b: List[Dict[str, Any]],
                      doc_a_name: str, doc_b_name: str) -> ComparisonResult:
    """Rule-based document comparison (Stage 2, no LLM) via difflib text
    similarity. Replaces sending both documents' full clause text to an LLM
    in a single prompt — the worst prompt-size offender in the pipeline."""
    if not clauses_a and not clauses_b:
        return ComparisonResult(
            similarity_score=100, change_summary="Both documents are empty.",
            added_clauses=[], removed_clauses=[], modified_clauses=[],
            risk_changes="No clauses to compare.", difference_report="N/A",
        )

    remaining_b = list(clauses_b)
    unchanged, modified, removed = [], [], []
    diff_snippets = []
    ratios = []

    for a in clauses_a:
        a_text = a.get("text_content", "")
        a_name = a.get("section_name", "Unknown")

        best_idx, best_ratio = None, 0.0
        for idx, b in enumerate(remaining_b):
            ratio = difflib.SequenceMatcher(None, a_text, b.get("text_content", "")).ratio()
            if ratio > best_ratio:
                best_ratio, best_idx = ratio, idx

        if best_idx is not None and best_ratio >= MODIFIED_THRESHOLD:
            b = remaining_b.pop(best_idx)
            ratios.append(best_ratio)
            if best_ratio >= UNCHANGED_THRESHOLD:
                unchanged.append(a_name)
            else:
                modified.append(a_name)
                diff_lines = list(difflib.unified_diff(
                    a_text.splitlines(), b.get("text_content", "").splitlines(),
                    fromfile=f"A: {a_name}", tofile=f"B: {b.get('section_name', 'Unknown')}", lineterm="",
                ))
                diff_snippets.append("\n".join(diff_lines[:12]))
        else:
            removed.append(a_name)
            ratios.append(0.0)

    added = [b.get("section_name", "Unknown") for b in remaining_b]
    similarity_score = round(100 * (sum(ratios) / len(ratios))) if ratios else 0

    dist_a, dist_b = _risk_distribution(clauses_a), _risk_distribution(clauses_b)
    risk_changes = (
        f"Document A risk distribution: {dict(dist_a)}. Document B risk distribution: {dict(dist_b)}. "
        f"High-risk clause count changed from {dist_a.get('High', 0)} to {dist_b.get('High', 0)}."
    )

    change_summary = (
        f"Comparing '{doc_a_name}' to '{doc_b_name}': {len(unchanged)} clauses unchanged, "
        f"{len(modified)} modified, {len(removed)} removed, {len(added)} added. "
        f"Overall textual similarity: {similarity_score}%."
    )

    difference_report = (
        "\n\n".join(diff_snippets) if diff_snippets
        else "No materially modified clauses were detected between the two documents."
    )

    return ComparisonResult(
        similarity_score=similarity_score,
        change_summary=change_summary,
        added_clauses=added,
        removed_clauses=removed,
        modified_clauses=modified,
        risk_changes=risk_changes,
        difference_report=difference_report,
    )
