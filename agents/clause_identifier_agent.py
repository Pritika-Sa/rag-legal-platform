import re
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from agents.parser_agent import _is_section_heading
from agents.rule_engine import CLAUSE_RULES, detect_clause_type, generate_clause_title

# Re-exported for backward compatibility with any code importing CLAUSE_RULES
# from this module directly.
__all__ = ["CLAUSE_RULES", "IdentifiedClause", "identify_clauses"]

# A block must clear this confidence bar to be reported as an identified
# clause of a specific type (see rule_engine.detect_clause_type scoring).
MIN_CONFIDENCE = 0.3

# A candidate block shorter than this is almost never a real, standalone
# provision (a stray number, a lone heading word) -- filtered before it
# ever reaches detect_clause_type. Lower than the old 30-char bar because
# fine-grained segmentation (numbered/lettered/bulleted items, single table
# rows) legitimately produces short-but-real provisions, e.g. "IDV: Rs.
# 5,00,000." or a one-line "Premium: Rs. 12,340" table row.
MIN_BLOCK_CHARS = 15

# Two candidate blocks are treated as the same clause if their normalized
# text similarity is at least this high -- catches the common insurance-
# document pattern of the same declaration/condition appearing near-
# verbatim in both the Proposal Form and the Policy Schedule.
DEDUP_SIMILARITY_THRESHOLD = 0.90

# Any digit sequence -- amounts, percentages, dates, durations. Two blocks
# that are otherwise near-identical text but disagree on even one of these
# are NOT duplicates: "penalty of 8%" vs "penalty of 2%" is boilerplate that
# is 99% textually similar and 100% legally different. Deduping on text
# similarity alone silently discarded exactly this case (verified: a
# same-confidence Payment clause differing only in the penalty percentage
# was dropped as a "duplicate", eliminating a distinct financial term
# contradiction_agent.py's own duplicate/conflict detection is specifically
# built to catch). Comparing the full multiset of numeric tokens is a
# minimal, conservative guard: any numeric disagreement blocks the merge.
_NUMERIC_TOKEN_RE = re.compile(r'\d+(?:[.,]\d+)*%?')


def _numeric_fingerprint(text: str) -> tuple:
    return tuple(sorted(_NUMERIC_TOKEN_RE.findall(text)))

_BLANK_LINE_RE = re.compile(r'\n\s*\n+')
# Numbered sub-items starting a new line: "1. Foo", "1.1) Foo", "(1) Foo"
_NUMBERED_MARKER_RE = re.compile(r'\n(?=\s*(?:\d+(?:\.\d+)*[\.\)]\s+|\(\d+\)\s+))')
# Lettered sub-items starting a new line: "A. Foo", "a) Foo", "(a) Foo"
_LETTERED_MARKER_RE = re.compile(r'\n(?=\s*(?:[A-Za-z][\.\)]\s+|\([A-Za-z]\)\s+))')
# Bullet points starting a new line: "• Foo", "- Foo", "* Foo"
_BULLET_MARKER_RE = re.compile(r'\n(?=\s*[•▪◦‣·\-\*]\s+\S)')


class IdentifiedClause(BaseModel):
    clause_type: str
    clause_title: str
    clause_text: str
    confidence_score: float
    page_number: Optional[int] = None
    start_position: int
    end_position: int


def _extract_heading(block: str) -> Optional[str]:
    """Returns the block's own first line if it looks like a real document
    heading (short, Title-Case/ALL-CAPS/numbered — see parser_agent's
    heading patterns) and there's actual body text after it. Reuses the same
    detector parser_agent already applies when first segmenting the raw
    document, so a heading recognized there is recognized here too."""
    first_line, _, rest = block.partition("\n")
    first_line = first_line.strip()
    if first_line and rest.strip() and _is_section_heading(first_line):
        return first_line
    return None


def _split_on_inline_markers(text: str) -> List[str]:
    """Splits a block on numbered (1., 1.1, (1)), lettered (A., (a)), and
    bulleted (•, -, *) sub-item markers that begin a new line — these mark
    separate legal provisions bundled under one heading/paragraph, which the
    old blank-line-only splitter left fused together into one oversized
    block (the root cause of a whole 'Conditions of Coverage' section
    scoring as a single low-confidence 'General' clause instead of yielding
    one candidate per covered peril)."""
    pieces = [text]
    for marker_re in (_NUMBERED_MARKER_RE, _LETTERED_MARKER_RE, _BULLET_MARKER_RE):
        next_pieces = []
        for piece in pieces:
            next_pieces.extend(marker_re.split(piece))
        pieces = next_pieces
    return pieces


def _split_on_embedded_headings(text: str) -> List[str]:
    """Splits a block wherever one of its own internal lines itself looks
    like a section heading (reuses parser_agent's heading detector). Catches
    sub-headings ('Claims Procedure', 'Notice of Cancellation') that
    parse_document's coarser, page-level segmentation left bundled inside a
    larger section's body text instead of starting a new one."""
    lines = text.split("\n")
    if len(lines) < 3:
        return [text]
    pieces = []
    current = [lines[0]]
    for line in lines[1:]:
        if current and _is_section_heading(line.strip()):
            pieces.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        pieces.append("\n".join(current))
    return pieces


def _segment_into_clause_candidates(full_text: str) -> List[str]:
    """Turns raw document text into fine-grained, single-provision candidate
    blocks for clause-type scoring: split on blank lines (paragraph/table-row
    boundaries), then on embedded sub-headings, then on numbered/lettered/
    bulleted markers. Replaces the old blank-line-or-bare-numbered-paragraph
    split, which left large multi-topic sections as a single candidate and
    starved most real provisions of a fair shot at detect_clause_type."""
    candidates = []
    for paragraph in _BLANK_LINE_RE.split(full_text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for heading_piece in _split_on_embedded_headings(paragraph):
            for marker_piece in _split_on_inline_markers(heading_piece):
                cleaned = marker_piece.strip()
                if cleaned:
                    candidates.append(cleaned)
    return candidates


def _normalize_for_dedup(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip().lower())


def _deduplicate_clauses(clauses: List[IdentifiedClause]) -> List[IdentifiedClause]:
    """Collapses near-duplicate clauses (e.g. the same declaration repeated
    in both the Proposal Form and the Policy Schedule) down to one
    representative copy, keeping whichever duplicate scored the higher
    confidence. Length-gated before the expensive similarity check so this
    stays cheap even on documents with a few hundred candidate clauses.
    Never merges two blocks whose numeric fingerprints differ (see
    _numeric_fingerprint) -- text similarity alone is not enough evidence
    that two clauses carrying different amounts/percentages/dates are the
    same provision."""
    kept: List[IdentifiedClause] = []
    kept_norms: List[str] = []
    kept_fingerprints: List[tuple] = []

    for clause in clauses:
        norm = _normalize_for_dedup(clause.clause_text)
        fingerprint = _numeric_fingerprint(clause.clause_text)
        duplicate_index = None
        for i, existing_norm in enumerate(kept_norms):
            if fingerprint != kept_fingerprints[i]:
                continue
            longer = max(len(norm), len(existing_norm), 1)
            if abs(len(norm) - len(existing_norm)) > 0.3 * longer:
                continue
            if SequenceMatcher(None, norm, existing_norm).ratio() >= DEDUP_SIMILARITY_THRESHOLD:
                duplicate_index = i
                break

        if duplicate_index is None:
            kept.append(clause)
            kept_norms.append(norm)
            kept_fingerprints.append(fingerprint)
        elif clause.confidence_score > kept[duplicate_index].confidence_score:
            kept[duplicate_index] = clause
            kept_norms[duplicate_index] = norm
            kept_fingerprints[duplicate_index] = fingerprint

    return kept


def identify_clauses(full_text: str, page_mapping: Optional[List[Dict[str, Any]]] = None) -> List[IdentifiedClause]:
    """Identifies clauses using regex + keyword rule scoring (Stage 2, no LLM).

    Segments full_text into fine-grained candidate blocks (see
    _segment_into_clause_candidates: blank lines, embedded sub-headings, and
    numbered/lettered/bulleted markers), scores each against every clause
    type in CLAUSE_RULES via rule_engine.detect_clause_type, keeps the
    single best-scoring type if it clears MIN_CONFIDENCE, then deduplicates
    near-identical results across the document.
    """
    identified_clauses = []
    candidate_blocks = _segment_into_clause_candidates(full_text)

    def find_page_number(clause_text):
        if not page_mapping:
            return None
        for mapping in page_mapping:
            if clause_text.lower() in mapping["text_content"].lower():
                return mapping["page_number"]
        return None

    processed_blocks = set()

    for block in candidate_blocks:
        if len(block) < MIN_BLOCK_CHARS or block in processed_blocks:
            continue

        clause_type, confidence = detect_clause_type(block)
        if clause_type == "General" or confidence < MIN_CONFIDENCE:
            continue

        start_pos = full_text.find(block)
        if start_pos == -1:
            start_pos = 0
        end_pos = start_pos + len(block)
        page_num = find_page_number(block)

        # Prefer the document's own heading when the block clearly has one;
        # otherwise generate a descriptive title from the clause type/content.
        # Either way, this is never the bare clause_type — that stays a
        # separate field reserved for grouping/filtering/analytics, not display.
        clause_title = _extract_heading(block) or generate_clause_title(clause_type, block)

        identified_clauses.append(IdentifiedClause(
            clause_type=clause_type,
            clause_title=clause_title,
            clause_text=block,
            confidence_score=confidence,
            page_number=page_num,
            start_position=start_pos,
            end_position=end_pos,
        ))
        processed_blocks.add(block)

    identified_clauses = _deduplicate_clauses(identified_clauses)

    # Guarantee document-wide uniqueness: two different clauses must never
    # display the same title, even if both lack a heading and land on the
    # same generated fallback (e.g. two un-headed Confidentiality clauses
    # both falling through to "Confidentiality Obligations").
    title_counts: Dict[str, int] = {}
    for clause in identified_clauses:
        title_counts[clause.clause_title] = title_counts.get(clause.clause_title, 0) + 1
        if title_counts[clause.clause_title] > 1:
            clause.clause_title = f"{clause.clause_title} ({title_counts[clause.clause_title]})"

    return identified_clauses


def backfill_clause_title(classification: str, text_content: str) -> str:
    """Regenerates a display title for a clause that was persisted before
    clause_title generation existed (its section_name is the bare category
    name — the exact bug this whole module fixes). Same logic identify_clauses
    applies to freshly-identified clauses: prefer a real heading if the
    clause's own text happens to start with one, else generate one from the
    category/content. No LLM call."""
    return _extract_heading(text_content or "") or generate_clause_title(classification or "General", text_content or "")


def backfill_clause_titles_for_document(doc_id) -> int:
    """One-time migration for a single document's already-persisted clauses:
    any clause whose stored section_name is still literally its bare
    classification (case-insensitive) — i.e. ingested before clause_title
    generation existed — gets a real title regenerated and written back.
    Clauses that already have a real, distinct title are left untouched.
    Returns the number of clauses updated. Callers should gate this behind a
    per-document flag so it only runs once (see views/clause_analysis.py and
    views/risk_analysis.py)."""
    from database import crud

    clauses = crud.get_clauses_for_document(doc_id)
    existing_titles = {(c.get("section_name") or "").strip().lower() for c in clauses}
    updated = 0

    for c in clauses:
        section_name = (c.get("section_name") or "").strip()
        classification = (c.get("classification") or "").strip()
        if not classification or section_name.lower() != classification.lower():
            continue  # already has a real, distinct title — don't touch it

        base_title = backfill_clause_title(classification, c.get("text_content") or "")
        new_title = base_title
        suffix = 2
        while new_title.lower() in existing_titles:
            new_title = f"{base_title} ({suffix})"
            suffix += 1

        existing_titles.discard(section_name.lower())
        existing_titles.add(new_title.lower())
        crud.update_clause_title(c["id"], new_title)
        updated += 1

    return updated
