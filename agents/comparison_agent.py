import difflib
from collections import Counter
from typing import Any, Dict, List, Tuple

import numpy as np
from pydantic import BaseModel, Field
from scipy.optimize import linear_sum_assignment

from agents.rule_engine import extract_clause_number, normalize_clause_title
from services.semantic_similarity import cosine_similarity_matrix, embed_texts

UNCHANGED_THRESHOLD = 0.97
MODIFIED_THRESHOLD = 0.55

# Hybrid similarity weighting for clause-to-clause matching: text similarity
# alone (difflib) misses paraphrased clauses (same meaning, different
# wording), and embedding similarity alone misses clauses that just had a
# figure/date changed (paraphrase-similar but the actual conflict). Blending
# both catches either case.
TEXT_SIMILARITY_WEIGHT = 0.5
EMBEDDING_SIMILARITY_WEIGHT = 0.5

# A "clause title" shared by more than this many clauses on either side is
# almost certainly not a genuine repeated heading — section_name is
# sometimes populated from the detected clause TYPE rather than the
# document's real heading text (see agents/orchestrator.py), so e.g. every
# clause in an NDA classified as "Confidentiality" would otherwise force-pair
# by coincidence rather than by actual best match. Above this size, title
# matching is skipped and the clause falls through to the hybrid
# similarity + Hungarian assignment pass instead, which judges the real
# content rather than a coincidentally shared label.
MAX_TITLE_GROUP_SIZE = 4


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


def _enrich(clause: Dict[str, Any]) -> Dict[str, Any]:
    section_name = clause.get("section_name", "Unknown")
    text = clause.get("text_content", "") or ""
    return {
        "section_name": section_name,
        "text": text,
        "clause_number": extract_clause_number(section_name, text),
        "title_key": normalize_clause_title(section_name),
    }


def _key_match_pairs(
    enriched_a: List[Dict[str, Any]], enriched_b: List[Dict[str, Any]]
) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
    """Pass 1: force-pair clauses that share the same clause number or the
    same normalized title — the same high-confidence signal
    contradiction_agent uses for duplicate grouping. This is preferred over
    similarity scoring wherever it's available, since a renumbered-but-barely
    reworded clause and a same-numbered-but-heavily-rewritten clause should
    both still be recognized as "the same clause, modified" rather than
    risking a similarity-score mismatch. Returns (matched (a_idx, b_idx)
    pairs, remaining a indices, remaining b indices)."""
    by_number: Dict[str, List[int]] = {}
    by_title: Dict[str, List[int]] = {}
    for j, b in enumerate(enriched_b):
        if b["clause_number"]:
            by_number.setdefault(b["clause_number"], []).append(j)
        if b["title_key"]:
            by_title.setdefault(b["title_key"], []).append(j)

    title_count_a = Counter(a["title_key"] for a in enriched_a if a["title_key"])

    matched: List[Tuple[int, int]] = []
    used_b: set = set()
    for i, a in enumerate(enriched_a):
        candidate = None
        if a["clause_number"]:
            for j in by_number.get(a["clause_number"], []):
                if j not in used_b:
                    candidate = j
                    break
        title_ambiguous = (
            title_count_a[a["title_key"]] > MAX_TITLE_GROUP_SIZE
            or len(by_title.get(a["title_key"], [])) > MAX_TITLE_GROUP_SIZE
        )
        if candidate is None and a["title_key"] and not title_ambiguous:
            for j in by_title.get(a["title_key"], []):
                if j not in used_b:
                    candidate = j
                    break
        if candidate is not None:
            matched.append((i, candidate))
            used_b.add(candidate)

    matched_a = {i for i, _ in matched}
    remaining_a = [i for i in range(len(enriched_a)) if i not in matched_a]
    remaining_b = [j for j in range(len(enriched_b)) if j not in used_b]
    return matched, remaining_a, remaining_b


def _hybrid_similarity_matrix(
    subset_a: List[Dict[str, Any]], subset_b: List[Dict[str, Any]]
) -> Tuple[np.ndarray, np.ndarray]:
    """Returns (hybrid_matrix, text_ratio_matrix) for every subset_a x
    subset_b pair. hybrid blends difflib text similarity with embedding
    (meaning) similarity so paraphrased clauses aren't invisible to matching;
    text_ratio is kept separately since "unchanged" (near-identical wording)
    is judged on raw text, not meaning."""
    texts_a = [c["text"] for c in subset_a]
    texts_b = [c["text"] for c in subset_b]

    text_ratio = np.array([
        [difflib.SequenceMatcher(None, ta, tb).ratio() for tb in texts_b]
        for ta in texts_a
    ]) if texts_a and texts_b else np.zeros((len(texts_a), len(texts_b)))

    embed_sim = cosine_similarity_matrix(embed_texts(texts_a), embed_texts(texts_b))

    hybrid = TEXT_SIMILARITY_WEIGHT * text_ratio + EMBEDDING_SIMILARITY_WEIGHT * embed_sim
    return hybrid, text_ratio


def _optimal_match_pairs(
    enriched_a: List[Dict[str, Any]], remaining_a: List[int],
    enriched_b: List[Dict[str, Any]], remaining_b: List[int],
) -> Tuple[List[Tuple[int, int, float, float]], List[int], List[int]]:
    """Pass 2: for clauses left unmatched by clause number/title, find the
    single globally-best pairing (Hungarian algorithm) over the hybrid
    similarity matrix, instead of greedily walking Document A in order and
    grabbing whichever remaining B clause scores highest so far — the greedy
    approach is order-dependent and easily mismatches clauses when several
    score similarly (e.g. boilerplate sections). Assignments scoring below
    MODIFIED_THRESHOLD are rejected (too dissimilar to be "the same clause,
    modified") and fall back to removed/added instead of a forced weak match.
    Returns (accepted (a_idx, b_idx, hybrid_score, text_ratio) tuples, final
    unmatched a indices, final unmatched b indices)."""
    if not remaining_a or not remaining_b:
        return [], remaining_a, remaining_b

    subset_a = [enriched_a[i] for i in remaining_a]
    subset_b = [enriched_b[j] for j in remaining_b]
    hybrid, text_ratio = _hybrid_similarity_matrix(subset_a, subset_b)

    row_ind, col_ind = linear_sum_assignment(hybrid, maximize=True)

    accepted = []
    accepted_a_local, accepted_b_local = set(), set()
    for r, c in zip(row_ind, col_ind):
        if hybrid[r, c] >= MODIFIED_THRESHOLD:
            accepted.append((remaining_a[r], remaining_b[c], float(hybrid[r, c]), float(text_ratio[r, c])))
            accepted_a_local.add(r)
            accepted_b_local.add(c)

    unmatched_a = [remaining_a[r] for r in range(len(remaining_a)) if r not in accepted_a_local]
    unmatched_b = [remaining_b[c] for c in range(len(remaining_b)) if c not in accepted_b_local]
    return accepted, unmatched_a, unmatched_b


def compare_documents(clauses_a: List[Dict[str, Any]], clauses_b: List[Dict[str, Any]],
                      doc_a_name: str, doc_b_name: str) -> ComparisonResult:
    """Rule-based document comparison (Stage 2, no LLM). Matches clauses in
    two passes:

      1. Force-pair clauses sharing the same clause number or normalized
         title (see _key_match_pairs).
      2. For everything left, blend text similarity (difflib) with embedding
         similarity into one hybrid score, then solve the globally-optimal
         one-to-one pairing (scipy's Hungarian algorithm) instead of a
         greedy, order-dependent nearest-match loop (see
         _optimal_match_pairs) — this is what lets paraphrased clauses (same
         meaning, different wording) still be recognized as "modified"
         rather than incorrectly falling out as one removed + one added
         clause.

    Never sends both documents' full clause text to an LLM in one prompt —
    the worst prompt-size offender the original design replaced.
    """
    if not clauses_a and not clauses_b:
        return ComparisonResult(
            similarity_score=100, change_summary="Both documents are empty.",
            added_clauses=[], removed_clauses=[], modified_clauses=[],
            risk_changes="No clauses to compare.", difference_report="N/A",
        )

    enriched_a = [_enrich(c) for c in clauses_a]
    enriched_b = [_enrich(c) for c in clauses_b]

    key_matched, remaining_a, remaining_b = _key_match_pairs(enriched_a, enriched_b)
    optimal_matched, unmatched_a, unmatched_b = _optimal_match_pairs(
        enriched_a, remaining_a, enriched_b, remaining_b
    )

    # Normalize both passes into one (a_idx, b_idx, hybrid_score, text_ratio)
    # list. Key-matched pairs don't have a hybrid score yet — compute it the
    # same way pass 2 does, so severity/scoring is consistent regardless of
    # which pass found the match.
    matched: List[Tuple[int, int, float, float]] = list(optimal_matched)
    if key_matched:
        km_hybrid, km_text_ratio = _hybrid_similarity_matrix(
            [enriched_a[i] for i, _ in key_matched], [enriched_b[j] for _, j in key_matched]
        )
        for k, (i, j) in enumerate(key_matched):
            matched.append((i, j, float(km_hybrid[k, k]), float(km_text_ratio[k, k])))

    unchanged, modified, diff_snippets, ratios = [], [], [], []
    for a_idx, b_idx, hybrid_score, text_ratio in matched:
        a, b = enriched_a[a_idx], enriched_b[b_idx]
        ratios.append(hybrid_score)
        if text_ratio >= UNCHANGED_THRESHOLD:
            unchanged.append(a["section_name"])
        else:
            modified.append(a["section_name"])
            diff_lines = list(difflib.unified_diff(
                a["text"].splitlines(), b["text"].splitlines(),
                fromfile=f"A: {a['section_name']}", tofile=f"B: {b['section_name']}", lineterm="",
            ))
            diff_snippets.append("\n".join(diff_lines[:12]))

    removed = [enriched_a[i]["section_name"] for i in unmatched_a]
    ratios.extend([0.0] * len(removed))
    added = [enriched_b[j]["section_name"] for j in unmatched_b]

    similarity_score = round(100 * (sum(ratios) / len(ratios))) if ratios else 0

    dist_a, dist_b = _risk_distribution(clauses_a), _risk_distribution(clauses_b)
    risk_changes = (
        f"Document A risk distribution: {dict(dist_a)}. Document B risk distribution: {dict(dist_b)}. "
        f"High-risk clause count changed from {dist_a.get('High', 0)} to {dist_b.get('High', 0)}."
    )

    change_summary = (
        f"Comparing '{doc_a_name}' to '{doc_b_name}': {len(unchanged)} clauses unchanged, "
        f"{len(modified)} modified, {len(removed)} removed, {len(added)} added. "
        f"Overall similarity (text + meaning): {similarity_score}%."
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
