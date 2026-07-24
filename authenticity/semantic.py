"""Factor 7 of the Authenticity Verification Engine: Semantic Consistency.

Reworked 2026-07-20 to be document-structure aware. The original version
always scored heading-to-body cosine similarity — reasonable for a prose
contract clause ("Termination" heading, a paragraph of termination
language) but structurally unfair to highly structured documents (an
insurance policy's field/table rows, a certificate, a coverage schedule):
a heading like "Engine Number" next to a bare value like "ABCD1234EFGH" has
near-zero embedding similarity to its own heading *by construction* — there
is no prose relationship to measure — which used to drag the whole
document's score down for reasons that have nothing to do with tampering.

New behavior: this factor first measures how much of the document is prose
vs. structured field/table content (the same `_looks_like_prose` filter
already used to exclude non-prose rows from the old mean). If the document
is PRIMARILY structured (more non-prose clauses than prose ones),
heading-body similarity is not computed at all for scoring purposes —
replaced with two structural checks that are meaningful for that kind of
content: field completeness (are the document's own fields actually filled
in, not blank/placeholder) and section ordering (do numbered sections
appear in a sane, non-decreasing order). If the document is primarily
prose, heading-body similarity remains exactly as before, unchanged.

This adapts automatically to document TYPE without hardcoding any type
name here or duplicating authenticity/type_validators/: an Insurance
Policy, an Invoice, or an Identity Document will each naturally trip the
"primarily structured" branch because of how much of their content is
field/table rows rather than prose, while an Employment Contract or NDA
will naturally stay in the prose branch — the adaptation is driven by the
document's own measured characteristics, not a per-type lookup table.
Table consistency / identifier consistency across fields is deliberately
NOT reimplemented here — that is authenticity/cross_field.py's job
(Factor 3) and authenticity/type_validators/'s job (Factor 8); duplicating
either here would be redundant, not additive.
"""

import logging
import re
from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field

from services.semantic_similarity import cosine_similarity_matrix, embed_texts
from utils.confidence import evidence_confidence

logger = logging.getLogger(__name__)

WORST_N_IN_EVIDENCE = 3
MIN_PROSE_WORDS = 4
_WORD_RE = re.compile(r"[A-Za-z]{2,}")

# A document is treated as "primarily structured" (table/field/certificate
# style) rather than "primarily prose" (ordinary contract clauses) when
# more than this fraction of its clauses are non-prose. A plain, symmetric
# majority cutoff -- not tuned against any specific sample document.
STRUCTURED_DOCUMENT_THRESHOLD = 0.5

_LEADING_NUM_RE = re.compile(r"^\s*(\d+)(?:\.\d+)*")
_PLACEHOLDER_VALUE_RE = re.compile(
    r"^[\s\-_.:]*$|^(n/?a|tbd|none|pending|to be (?:filled|determined|confirmed))[\s.]*$", re.IGNORECASE,
)


def _looks_like_prose(text: str) -> bool:
    return len(_WORD_RE.findall(text)) >= MIN_PROSE_WORDS


def _looks_like_populated_value(text: str) -> bool:
    """A structured field's body counts as 'complete' if it has any real
    content beyond a blank/placeholder marker ("", "-", "N/A", "TBD", ...).
    An empty or placeholder value in a field that the document itself
    declares (via its own heading) is a genuine completeness gap -- unlike
    a prose document simply not mentioning something, a structured
    document's own labelled field being blank is evidence worth surfacing."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    return not bool(_PLACEHOLDER_VALUE_RE.match(stripped))


def _field_completeness_score(non_prose_clauses: List[Dict[str, Any]]) -> Optional[float]:
    if not non_prose_clauses:
        return None
    complete = sum(1 for c in non_prose_clauses if _looks_like_populated_value(c.get("text_content", "")))
    return complete / len(non_prose_clauses)


def _section_ordering_score(clauses: List[Dict[str, Any]]) -> Optional[float]:
    """1.0 if every leading section number is non-decreasing, 0.0 if any
    number is smaller than one that appeared before it (broken ordering --
    the same signal the retired flat-deduction scorer used, reused here as
    one structural-consistency input among several rather than a standalone
    fixed deduction). None ("not checkable") when fewer than 2 clauses carry
    a leading number at all."""
    numbers = []
    for c in clauses:
        match = _LEADING_NUM_RE.match((c.get("section_name") or "").strip())
        if match:
            numbers.append(int(match.group(1)))
    if len(numbers) < 2:
        return None
    broken = any(numbers[i] < numbers[i - 1] for i in range(1, len(numbers)))
    return 0.0 if broken else 1.0


class ClauseSemanticMatch(BaseModel):
    section_name: str
    similarity: float


class SemanticConsistencyFactorResult(BaseModel):
    applicable: bool = Field(description="False when there is no usable content (prose or structured) to evaluate")
    score: float = Field(description="0-1. Prose documents: mean heading-body cosine similarity. Structured documents: mean of field-completeness / section-ordering signals.")
    confidence: float = Field(description="0-100")
    mode: str = Field(default="prose", description="'prose' (heading-body similarity) or 'structured' (field/ordering checks)")
    checked: List[ClauseSemanticMatch] = Field(default_factory=list, description="Populated only in prose mode.")
    evidence: List[str] = Field(default_factory=list)


def _not_applicable(reason: str) -> SemanticConsistencyFactorResult:
    return SemanticConsistencyFactorResult(applicable=False, score=0.0, confidence=0.0, evidence=[reason])


def _assess_prose_mode(usable: List[Dict[str, Any]], skipped_non_prose: int) -> SemanticConsistencyFactorResult:
    headings = [c["section_name"] for c in usable]
    bodies = [c["text_content"] for c in usable]

    heading_vecs = embed_texts(headings)
    body_vecs = embed_texts(bodies)
    sim_matrix = cosine_similarity_matrix(heading_vecs, body_vecs)
    similarities = [float(np.clip(sim_matrix[i, i], 0.0, 1.0)) for i in range(len(usable))]

    checked = [
        ClauseSemanticMatch(section_name=usable[i].get("section_name", ""), similarity=round(similarities[i], 4))
        for i in range(len(usable))
    ]
    score = round(sum(similarities) / len(similarities), 4)
    confidence = round(100.0 * evidence_confidence(len(usable)), 2)

    worst = sorted(checked, key=lambda c: c.similarity)[:WORST_N_IN_EVIDENCE]
    skip_note = f" ({skipped_non_prose} non-prose field-value clause(s) skipped)" if skipped_non_prose else ""
    evidence = [
        "Document is primarily prose; applied heading-body semantic similarity.",
        f"Checked {len(usable)} clause(s){skip_note}; mean heading-body semantic similarity {score:.2f}.",
    ]
    evidence += [f"Lowest match: '{w.section_name}' (similarity {w.similarity:.2f})." for w in worst]

    logger.debug(f"[semantic] mode=prose usable={len(usable)} skipped_non_prose={skipped_non_prose} score={score:.4f} confidence={confidence:.2f}")

    return SemanticConsistencyFactorResult(
        applicable=True, score=score, confidence=confidence, mode="prose", checked=checked, evidence=evidence,
    )


def _assess_structured_mode(
    candidates: List[Dict[str, Any]], non_prose: List[Dict[str, Any]], document_type: Optional[str],
) -> SemanticConsistencyFactorResult:
    field_score = _field_completeness_score(non_prose)
    order_score = _section_ordering_score(candidates)

    signals = [("field_completeness", field_score), ("section_ordering", order_score)]
    usable_signals = [(name, val) for name, val in signals if val is not None]

    type_label = document_type or "structured document"
    evidence = [
        f"Structured {type_label} detected ({len(non_prose)}/{len(candidates)} clauses are field/table-value "
        f"content, not prose). Applied table-aware structural evaluation.",
        "Heading-body semantic similarity ignored because the document is primarily structured, not prose.",
    ]

    if not usable_signals:
        logger.debug(f"[semantic] mode=structured document_type={document_type} no usable structural signal")
        return SemanticConsistencyFactorResult(
            applicable=True, score=0.0, confidence=0.0, mode="structured",
            evidence=evidence + ["No structural signal (field completeness or section ordering) was checkable."],
        )

    score = round(sum(val for _, val in usable_signals) / len(usable_signals), 4)
    confidence = round(100.0 * evidence_confidence(len(non_prose)), 2)

    if field_score is not None:
        complete_count = round(field_score * len(non_prose))
        evidence.append(
            f"Field completeness: {complete_count}/{len(non_prose)} structured field(s) have a real, "
            f"non-blank value ({field_score:.0%})."
        )
    if order_score is not None:
        evidence.append(
            "Section ordering: numbered sections are in non-decreasing order." if order_score >= 1.0
            else "Section ordering: a section number appears out of order relative to an earlier one."
        )
    else:
        evidence.append("Section ordering: not checkable (fewer than 2 numbered sections found).")

    logger.debug(
        f"[semantic] mode=structured document_type={document_type} "
        f"signals={dict(usable_signals)} score={score:.4f} confidence={confidence:.2f}"
    )

    return SemanticConsistencyFactorResult(
        applicable=True, score=score, confidence=confidence, mode="structured", evidence=evidence,
    )


def assess_semantic_consistency(
    clauses: List[Dict[str, Any]], document_type: Optional[str] = None,
) -> SemanticConsistencyFactorResult:
    candidates = [
        c for c in clauses
        if (c.get("section_name") or "").strip() and (c.get("text_content") or "").strip()
    ]
    if not candidates:
        return _not_applicable("No clauses with both a heading and body text were available to compare.")

    usable = [c for c in candidates if _looks_like_prose(c["text_content"])]
    non_prose = [c for c in candidates if not _looks_like_prose(c["text_content"])]
    structured_ratio = len(non_prose) / len(candidates)

    logger.debug(
        f"[semantic] document_type={document_type} candidates={len(candidates)} prose={len(usable)} "
        f"non_prose={len(non_prose)} structured_ratio={structured_ratio:.2f} "
        f"threshold={STRUCTURED_DOCUMENT_THRESHOLD}"
    )

    if structured_ratio > STRUCTURED_DOCUMENT_THRESHOLD:
        logger.debug(f"[semantic] adaptation_strategy=structured (ratio {structured_ratio:.2f} > {STRUCTURED_DOCUMENT_THRESHOLD})")
        return _assess_structured_mode(candidates, non_prose, document_type)

    if not usable:
        return _not_applicable(
            f"All {len(candidates)} clause(s) with a heading and body were non-prose field-value "
            f"content (e.g. codes, IDs, numbers) that heading-body semantic similarity can't "
            f"meaningfully assess."
        )

    logger.debug(f"[semantic] adaptation_strategy=prose (ratio {structured_ratio:.2f} <= {STRUCTURED_DOCUMENT_THRESHOLD})")
    return _assess_prose_mode(usable, len(non_prose))
