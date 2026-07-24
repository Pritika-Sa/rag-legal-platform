"""Factor 1 of the Authenticity Verification Engine: Document Structure
Validation. Score = a blend of section presence, section-numbering order,
and cross-page continuity for the document's type — replaces the old
agents/authenticity_agent.py's flat per-item deductions (see the redesign
proposal's Problem Statement for why a fixed -20/-15/-10 per missing item
can tank a genuine document over one unrecognized section).

Consumes Stage 0's output (services.document_classifier.classify_document_type_ranked)
to pick which section template to check against, but — reworked
2026-07-20 — no longer lets that classification's CONFIDENCE move the
SCORE. Document-type classification confidence answers "what type of
document is this?"; document structure answers "is this document
internally well organized?" Those are different questions: a genuinely
well-organized Insurance Policy with every section present must not score
lower just because the type classifier itself was only 60% sure it was
looking at an Insurance Policy specifically (as opposed to, say, a Motor
Certificate) — the sections are either there or they aren't, independent
of how confidently we guessed the type label. Classification confidence
now only affects this factor's CONFIDENCE (how much to trust the score),
never the score itself:

  - A template is registered for the classified type: the score is that
    template's own found/missing fraction, full weight, regardless of
    classification confidence.
  - No template registered for the type (or the type is genuinely
    Unknown Document): falls back to the generic-minimal template
    outright — a different situation ("we don't know what to check
    against at all"), not a confidence-blending one.

Beyond section presence, structure quality also now considers section-
numbering order (are numbered sections non-decreasing?) and cross-page
continuity (do the document's own page numbers form a contiguous run?)
when there is enough data to check either — genuinely new "is this
document well organized" evidence that has nothing to do with which
template was selected.

This module never assigns a manual point value to a missing section — the
detection patterns themselves are the only hand-authored content here,
identical in spirit to rules/clause_rules.json's keyword/regex vocabulary;
every score is always a plain fraction or mean of fractions.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from services.document_classifier import UNKNOWN_DOCUMENT_TYPE, DocumentTypeClassification
from utils.confidence import evidence_confidence

logger = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "document_structure_rules.json"
GENERIC_MINIMAL_KEY = "generic_minimal"

_LEADING_NUM_RE = re.compile(r"^\s*(\d+)(?:\.\d+)*")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _load_compiled_rules() -> Dict[str, List[Tuple[str, List["re.Pattern"]]]]:
    with _RULES_PATH.open(encoding="utf-8") as f:
        raw = json.load(f)
    return {
        doc_type: [
            (section["name"], [re.compile(p, re.IGNORECASE) for p in section["patterns"]])
            for section in entry["sections"]
        ]
        for doc_type, entry in raw.items()
    }


_COMPILED = _load_compiled_rules()
if GENERIC_MINIMAL_KEY not in _COMPILED:
    raise RuntimeError(f"document_structure_rules.json is missing its required '{GENERIC_MINIMAL_KEY}' template")


class StructureFactorResult(BaseModel):
    applicable: bool = Field(
        default=True,
        description="Always True — unlike most other factors, structure validation always "
                     "produces a real score via the generic-minimal fallback, even when no "
                     "type-specific template applies. Present for a uniform contract with the "
                     "other factors (authenticity/dai.py fuses all factors duck-typed on "
                     "applicable/score/confidence).",
    )
    score: float = Field(description="Mean of section-presence, section-numbering, and page-continuity signals (whichever are checkable), 0-1")
    confidence: float = Field(description="0-100")
    template_used: str
    found_sections: List[str] = Field(default_factory=list)
    missing_sections: List[str] = Field(default_factory=list)
    section_numbering_score: Optional[float] = Field(default=None, description="None if not checkable (fewer than 2 numbered sections)")
    page_continuity_score: Optional[float] = Field(default=None, description="None if not checkable (fewer than 2 real pages)")
    evidence: List[str] = Field(default_factory=list)


def _check_template(normalized_text: str, doc_type: str) -> Tuple[List[str], List[str]]:
    found, missing = [], []
    for name, patterns in _COMPILED[doc_type]:
        target = found if any(p.search(normalized_text) for p in patterns) else missing
        target.append(name)
    return found, missing


def _fraction(found: List[str], missing: List[str]) -> float:
    total = len(found) + len(missing)
    return (len(found) / total) if total else 0.0


def _section_numbering_score(clauses: Optional[List[Dict[str, Any]]]) -> Optional[float]:
    """1.0 if every leading section/clause number is non-decreasing, 0.0 if
    a number is smaller than one that appeared before it. None ("not
    checkable") when fewer than 2 clauses carry a leading number — same
    signal the retired flat-deduction scorer used (broken numbering),
    reused here as one structural-quality input among several instead of a
    standalone fixed deduction."""
    numbers = []
    for c in clauses or []:
        match = _LEADING_NUM_RE.match((c.get("section_name") or "").strip())
        if match:
            numbers.append(int(match.group(1)))
    if len(numbers) < 2:
        return None
    broken = any(numbers[i] < numbers[i - 1] for i in range(1, len(numbers)))
    return 0.0 if broken else 1.0


def _page_continuity_score(pages: Optional[List[Dict[str, Any]]]) -> Optional[float]:
    """Fraction of the page-number span actually accounted for — 1.0 for a
    contiguous 1..N run, degrading proportionally for gaps (e.g. pages
    [1, 2, 4]: a span of 4 with only 3 pages present -> 0.75). None ("not
    checkable") when fewer than 2 independently-extracted pages exist
    (DOCX/TXT sources, single-page PDFs)."""
    numbers = sorted({
        p.get("page_number") for p in (pages or [])
        if p.get("page_number") is not None and (p.get("raw_text") or "").strip()
    })
    if len(numbers) < 2:
        return None
    expected_span = numbers[-1] - numbers[0] + 1
    if expected_span <= 0:
        return None
    gaps = expected_span - len(numbers)
    return max(0.0, 1.0 - gaps / expected_span)


def _combine_structural_signals(
    section_presence_score: float,
    numbering_score: Optional[float],
    continuity_score: Optional[float],
) -> float:
    """Mean of whichever structural signals are actually checkable — the
    same coverage-based idiom used everywhere else in this engine (only
    average over what there was evidence to check, never treat an
    uncheckable signal as a strike). Section presence is always checkable
    (even the generic-minimal template always resolves to a fraction), so
    the mean always has at least one term."""
    signals = [section_presence_score]
    if numbering_score is not None:
        signals.append(numbering_score)
    if continuity_score is not None:
        signals.append(continuity_score)
    return sum(signals) / len(signals)


def assess_structure(
    full_text: str,
    classification: DocumentTypeClassification,
    clauses: Optional[List[Dict[str, Any]]] = None,
    pages: Optional[List[Dict[str, Any]]] = None,
) -> StructureFactorResult:
    normalized = _normalize(full_text or "")
    has_specific_template = (
        classification.document_type != UNKNOWN_DOCUMENT_TYPE
        and classification.document_type in _COMPILED
    )

    numbering_score = _section_numbering_score(clauses)
    continuity_score = _page_continuity_score(pages)
    logger.debug(
        f"[structure] document_type={classification.document_type} "
        f"classification_confidence={classification.confidence:.2f} "
        f"numbering_score={numbering_score} continuity_score={continuity_score}"
    )

    if not has_specific_template:
        found, missing = _check_template(normalized, GENERIC_MINIMAL_KEY)
        section_score = _fraction(found, missing)
        score = _combine_structural_signals(section_score, numbering_score, continuity_score)
        # No type signal to corroborate the template choice at all -- a
        # fixed 0.5 prior (the same "single uncorroborated piece of
        # evidence" reading evidence_confidence(1) would give) times how
        # much of the generic template was actually found.
        confidence = round(100.0 * 0.5 * evidence_confidence(len(found)), 2)
        reason = (
            f"No structure template is registered for '{classification.document_type}'; "
            f"checked the generic minimum (Title/Parties/Date/Signature) instead."
            if classification.document_type != UNKNOWN_DOCUMENT_TYPE
            else "Document type could not be confidently classified; checked the generic minimum instead."
        )
        evidence = [reason]
        evidence += [f"Found: {s}" for s in found] + [f"MISSING: {s}" for s in missing]
        evidence += _structural_signal_evidence(numbering_score, continuity_score)
        logger.debug(f"[structure] template=generic_minimal section_score={section_score:.4f} final_score={score:.4f} confidence={confidence:.2f}")
        return StructureFactorResult(
            score=round(score, 4), confidence=confidence, template_used=GENERIC_MINIMAL_KEY,
            found_sections=found, missing_sections=missing,
            section_numbering_score=numbering_score, page_continuity_score=continuity_score, evidence=evidence,
        )

    type_found, type_missing = _check_template(normalized, classification.document_type)
    section_score = _fraction(type_found, type_missing)
    score = _combine_structural_signals(section_score, numbering_score, continuity_score)

    c = classification.confidence
    # Confidence (how much to TRUST this score) still reflects classification
    # confidence and evidence coverage -- but, deliberately, the SCORE above
    # no longer does. See module docstring: "what type is this" (confidence)
    # is kept separate from "is it well organized" (score).
    confidence = round(100.0 * evidence_confidence(len(type_found)) * (0.5 + 0.5 * c), 2)

    evidence = [
        f"Applied the '{classification.document_type}' structure template "
        f"(type-classification confidence {c:.0%}) at full weight — classification confidence affects "
        f"how much this score is trusted (see confidence below), not the structure score itself.",
    ]
    evidence += [f"Found: {s}" for s in type_found] + [f"MISSING: {s}" for s in type_missing]
    evidence += _structural_signal_evidence(numbering_score, continuity_score)

    logger.debug(
        f"[structure] template={classification.document_type} section_score={section_score:.4f} "
        f"final_score={score:.4f} confidence={confidence:.2f} (decoupled from classification confidence)"
    )

    return StructureFactorResult(
        score=round(score, 4), confidence=confidence, template_used=classification.document_type,
        found_sections=type_found, missing_sections=type_missing,
        section_numbering_score=numbering_score, page_continuity_score=continuity_score, evidence=evidence,
    )


def _structural_signal_evidence(numbering_score: Optional[float], continuity_score: Optional[float]) -> List[str]:
    lines = []
    if numbering_score is None:
        lines.append("Section numbering: not checkable (fewer than 2 numbered sections found).")
    else:
        lines.append(
            "Section numbering: consistent, non-decreasing order." if numbering_score >= 1.0
            else "Section numbering: a section number appears out of order relative to an earlier one."
        )
    if continuity_score is None:
        lines.append("Page continuity: not checkable (fewer than 2 independently-extracted pages).")
    else:
        lines.append(
            "Page continuity: pages form a contiguous run." if continuity_score >= 1.0
            else f"Page continuity: {continuity_score:.0%} of the expected page span is accounted for (gaps detected)."
        )
    return lines
