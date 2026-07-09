import re
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from agents.rule_engine import CLAUSE_RULES, detect_clause_type

# Re-exported for backward compatibility with any code importing CLAUSE_RULES
# from this module directly.
__all__ = ["CLAUSE_RULES", "IdentifiedClause", "identify_clauses"]

# A block must clear this confidence bar to be reported as an identified
# clause of a specific type (see rule_engine.detect_clause_type scoring).
MIN_CONFIDENCE = 0.3


class IdentifiedClause(BaseModel):
    clause_type: str
    clause_text: str
    confidence_score: float
    page_number: Optional[int] = None
    start_position: int
    end_position: int


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

        identified_clauses.append(IdentifiedClause(
            clause_type=clause_type,
            clause_text=block,
            confidence_score=confidence,
            page_number=page_num,
            start_position=start_pos,
            end_position=end_pos,
        ))
        processed_blocks.add(block)

    return identified_clauses
