"""Factor 4 of the Authenticity Verification Engine: Entity Verification.

Checks whether the named parties/organizations that DO recur across the
document's pages stay CONSISTENT — the same issuer, the same customer, the
same vehicle/policy identifiers — everywhere they appear, rather than
scoring on how large a fraction of every distinct entity happens to recur.

Reworked 2026-07-20: the original version scored
`recurring_count / total_distinct_entities`, which unfairly penalized
highly structured documents (insurance policies, invoices) that legitimately
name many one-off administrative entities — a branch address, a broker's
contact name, a witness — each mentioned exactly once. A real insurance
policy with a perfectly consistent issuer/customer/policy number but a
dozen incidental one-off names used to score as low as ~20% under the old
formula, for reasons that have nothing to do with authenticity. A document
naming MORE entities is not more suspicious; what matters is whether the
entities that DO recur stay the same entity every time.

New model: entities mentioned only once ("administrative" entities) are
excluded from scoring entirely — same "not enough evidence to check, not a
strike against the document" posture Factor 3 (cross_field.py) already
uses for fields that don't repeat. Only entities recurring on 2+ pages
("key entities" — an issuer, a customer, a policy/vehicle identifier
naturally recur this way in any real multi-page document, regardless of
document type) are scored, and what's scored is NAME-FORM CONSISTENCY
across their own occurrences, not just binary recurrence. This is the
same generic mechanism regardless of document type — no per-type role list
(issuer/customer/vehicle/...) is hardcoded here; whatever actually recurs
in THIS document is what gets checked, which is exactly what the "issuer/
customer/vehicle/policy number consistency" checklist cashes out to at a
document-type-agnostic level without duplicating authenticity/type_validators/.
"""

import logging
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from agents.feature_extraction_agent import _SUBJECT_AGREEMENT_RATIO, _get_nlp, extract_entities
from utils.confidence import evidence_confidence

logger = logging.getLogger(__name__)

MIN_PAGES_FOR_CHECK = 2
PARTY_ENTITY_TYPES = {"PARTY", "ORG", "PERSON"}
MIN_SINGLE_WORD_NAME_LENGTH = 4

# An entity must be seen this many times before it's "key" (checkable for
# consistency) rather than "administrative" (mentioned once, excluded from
# scoring entirely — not a strike against the document).
MIN_OCCURRENCES_FOR_KEY_ENTITY = 2


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _looks_like_party_name(text: str) -> bool:
    """A real party name is either multi-word ("Bajaj Allianz General
    Insurance Company Limited") or a single, reasonably long, purely
    alphabetic word. Anything shorter or containing digits is far more
    likely a form field's value (a code, an ID, a serial number) that
    NER mis-tagged on noisy/tabular text than an actual party name."""
    stripped = text.strip()
    if not stripped:
        return False
    if " " in stripped:
        return True
    return len(stripped) >= MIN_SINGLE_WORD_NAME_LENGTH and stripped.isalpha()


def _same_entity(a: str, b: str) -> bool:
    # Reuses the exact fuzzy-match threshold agents.feature_extraction_agent
    # already established for "same real-world thing, worded slightly
    # differently" (there: dependency-parse subject vs. regex subject;
    # here: an entity name captured on two different pages) rather than
    # inventing a second threshold for a structurally identical judgment.
    return SequenceMatcher(None, a, b).ratio() >= _SUBJECT_AGREEMENT_RATIO


def _name_consistency_fraction(raw_mentions: List[str]) -> float:
    """Fraction of an entity's own raw-text mentions that fuzzy-match its
    own most common ("mode") surface form — the same OCR/formatting-
    tolerant "how consistent is this repeated value" idiom used by
    authenticity/cross_field.py and authenticity/type_validators/base.py,
    kept as its own small copy here (each factor keeps its own copy rather
    than importing another factor's private helper — same precedent
    cross_field.py and type_validators/base.py already set relative to
    each other)."""
    if not raw_mentions:
        return 0.0
    normalized = [_normalize(m) for m in raw_mentions]
    mode_value, _ = Counter(normalized).most_common(1)[0]
    matches = sum(1 for v in normalized if SequenceMatcher(None, v, mode_value).ratio() >= _SUBJECT_AGREEMENT_RATIO)
    return matches / len(normalized)


class EntityRecurrence(BaseModel):
    text: str
    pages_seen: List[int]
    recurring: bool
    name_consistency: float = Field(default=1.0, description="Fraction of this entity's own mentions that agree with its majority surface form, 0-1. Only meaningful when recurring=True.")


class EntityVerificationFactorResult(BaseModel):
    applicable: bool = Field(description="False when the document has fewer than 2 independently-extracted pages")
    score: float = Field(description="Mean name-consistency fraction across KEY (recurring, 2+ occurrence) entities only, 0-1. Entities mentioned once are excluded, never penalized.")
    confidence: float = Field(description="0-100")
    checked_entities: List[EntityRecurrence] = Field(default_factory=list)
    administrative_entity_count: int = Field(default=0, description="Distinct entities mentioned only once — excluded from scoring, not a penalty.")
    evidence: List[str] = Field(default_factory=list)


def assess_entity_verification(pages: List[Dict[str, Any]]) -> EntityVerificationFactorResult:
    real_pages = [p for p in pages if (p.get("raw_text") or "").strip()]
    if len(real_pages) < MIN_PAGES_FOR_CHECK:
        return EntityVerificationFactorResult(
            applicable=False, score=0.0, confidence=0.0,
            evidence=[
                f"Only {len(real_pages)} page(s) of independent text are available for this document "
                f"(DOCX/TXT sources and single-page PDFs have no page boundaries to check entity "
                f"recurrence across); this factor does not apply."
            ],
        )

    nlp = _get_nlp()
    groups: List[Dict[str, Any]] = []  # [{"display": str, "norm": str, "pages": set[int], "mentions": [str]}]

    for page in real_pages:
        page_number = page.get("page_number")
        doc = nlp(page["raw_text"])
        for entity in extract_entities(doc):
            if entity.entity_type not in PARTY_ENTITY_TYPES:
                continue
            if not _looks_like_party_name(entity.text):
                continue
            norm = _normalize(entity.text)
            if not norm:
                continue
            match = next((g for g in groups if _same_entity(norm, g["norm"])), None)
            if match is None:
                groups.append({"display": entity.text, "norm": norm, "pages": {page_number}, "mentions": [entity.text]})
            else:
                match["pages"].add(page_number)
                match["mentions"].append(entity.text)

    logger.debug(
        f"[entities] extracted {len(groups)} distinct party-like entities across {len(real_pages)} pages: "
        f"{[(g['display'], sorted(g['pages'])) for g in groups]}"
    )

    if not groups:
        return EntityVerificationFactorResult(
            applicable=True, score=0.0, confidence=0.0,
            evidence=["No named party entities were detected on any page."],
        )

    checked = [
        EntityRecurrence(
            text=g["display"],
            pages_seen=sorted(p for p in g["pages"] if p is not None),
            recurring=len(g["pages"]) >= MIN_OCCURRENCES_FOR_KEY_ENTITY,
            name_consistency=round(_name_consistency_fraction(g["mentions"]), 4) if len(g["pages"]) >= MIN_OCCURRENCES_FOR_KEY_ENTITY else 1.0,
        )
        for g in groups
    ]

    key_entities = [c for c in checked if c.recurring]
    administrative_entities = [c for c in checked if not c.recurring]

    logger.debug(
        f"[entities] key (recurring) entities: {[(c.text, c.name_consistency) for c in key_entities]}; "
        f"administrative (single-mention, excluded from scoring): {[c.text for c in administrative_entities]}"
    )

    plural = len(checked) != 1
    evidence = [
        f"Found {len(checked)} distinct named part{'ies' if plural else 'y'} across {len(real_pages)} pages; "
        f"{len(key_entities)} recur on 2+ pages and are scored, {len(administrative_entities)} appear once "
        f"and are excluded from scoring (not a penalty)."
    ]

    if not key_entities:
        # No entity recurs at all -- there is genuinely nothing to check
        # consistency of, which is different from "checked and found
        # inconsistent." Reported distinctly rather than silently scoring 0.
        for c in administrative_entities:
            evidence.append(f"ADMINISTRATIVE (single mention, no penalty): '{c.text}' seen on page(s) {c.pages_seen}.")
        result = EntityVerificationFactorResult(
            applicable=True, score=0.0, confidence=0.0, checked_entities=checked,
            administrative_entity_count=len(administrative_entities),
            evidence=evidence + ["No entity recurred across 2+ pages; nothing was available to check for consistency."],
        )
        logger.debug(f"[entities] final score=0.0 confidence=0.0 reason=no_recurring_entities")
        return result

    score = sum(c.name_consistency for c in key_entities) / len(key_entities)
    confidence = round(100.0 * evidence_confidence(len(key_entities)), 2)

    for c in key_entities:
        if c.name_consistency >= 1.0:
            evidence.append(f"CONSISTENT: '{c.text}' recurs on page(s) {c.pages_seen} with a stable name/form.")
        else:
            evidence.append(
                f"INCONSISTENT: '{c.text}' recurs on page(s) {c.pages_seen} but only "
                f"{c.name_consistency:.0%} of its mentions agree with each other."
            )
    for c in administrative_entities:
        evidence.append(f"ADMINISTRATIVE (single mention, no penalty): '{c.text}' seen on page(s) {c.pages_seen}.")
    if administrative_entities:
        evidence.append(
            f"No authenticity penalty applied for the {len(administrative_entities)} additional "
            f"administrative entit{'ies' if len(administrative_entities) != 1 else 'y'} above — a document "
            f"naming many one-off parties, addresses, or contacts is not, on its own, suspicious."
        )

    logger.debug(
        f"[entities] rule_scores={ {c.text: c.name_consistency for c in key_entities} } "
        f"final_score={score:.4f} confidence={confidence:.2f}"
    )

    return EntityVerificationFactorResult(
        applicable=True, score=round(score, 4), confidence=confidence, checked_entities=checked,
        administrative_entity_count=len(administrative_entities), evidence=evidence,
    )
