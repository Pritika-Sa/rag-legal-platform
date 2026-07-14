import re
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


def identify_clauses(full_text: str, page_mapping: Optional[List[Dict[str, Any]]] = None) -> List[IdentifiedClause]:
    """Identifies clauses using regex + keyword rule scoring (Stage 2, no LLM).

    For each paragraph block, scores it against every clause type in
    CLAUSE_RULES via rule_engine.detect_clause_type and keeps the single
    best-scoring type if it clears MIN_CONFIDENCE.
    """
    identified_clauses = []
    paragraphs = [p.strip() for p in re.split(r'\n\n|\n(?=\d+\.)', full_text) if p.strip()]

    def find_page_number(clause_text):
        if not page_mapping:
            return None
        for mapping in page_mapping:
            if clause_text.lower() in mapping["text_content"].lower():
                return mapping["page_number"]
        return None

    processed_blocks = set()

    for block in paragraphs:
        if len(block) < 30 or block in processed_blocks:
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
