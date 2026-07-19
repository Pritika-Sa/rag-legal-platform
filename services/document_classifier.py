"""Document Type Classifier (Stage 2, no LLM, no embeddings): a deterministic
regex/keyword classifier that runs once per document immediately after
parsing. The result is persisted to the documents collection by the caller
(agents/orchestrator.py), so this never needs to run twice for the same
document.

To add a new document type: add an entry to DOCUMENT_TYPE_PATTERNS with a
list of regex strings (case-insensitive, matched against the normalized
text). No other code needs to change.

classify_document_type() (the original function) returns just the winning
type name, unchanged — agents/orchestrator.py depends on that exact return
shape for the persisted document_type field. classify_document_type_ranked()
is additive: it exposes the runner-up and a confidence score computed from
information the original function already derives internally and discards
(the margin between the winning and second-place match counts). This is
Stage 0 of the Authenticity Verification Engine redesign — its confidence
propagates into the document-structure and mandatory-clause factors so an
ambiguous classification doesn't get treated with the same certainty as an
obvious one.
"""

import re
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from utils.confidence import evidence_confidence

UNKNOWN_DOCUMENT_TYPE = "Unknown Document"

# Minimum total pattern-match count required before a type is considered a
# confident match; below this the classifier returns UNKNOWN_DOCUMENT_TYPE
# rather than guessing.
MIN_CONFIDENT_SCORE = 1

DOCUMENT_TYPE_PATTERNS: Dict[str, List[str]] = {
    "Non-Disclosure Agreement (NDA)": [
        r"non[- ]?disclosure agreement",
        r"confidentiality agreement",
        r"confidential information",
        r"disclosing party",
        r"receiving party",
    ],
    "Employment Agreement": [
        r"employment agreement",
        r"\bemployee\b",
        r"\bemployer\b",
        r"probationary? period",
        r"\bsalary\b",
        r"letter of appointment",
    ],
    "Employment Contract": [
        r"employment contract",
        r"contract of employment",
        r"terms of employment",
        r"letter of employment",
    ],
    "Service Agreement": [
        r"service agreement",
        r"service provider",
        r"scope of work",
        r"\bdeliverables\b",
        r"statement of work",
    ],
    "Lease Agreement": [
        r"lease agreement",
        r"\blessor\b",
        r"\blessee\b",
        r"monthly rent",
        r"\bleasehold\b",
    ],
    "Rental Agreement": [
        r"rental agreement",
        r"\blandlord\b",
        r"\btenant\b",
        r"security deposit",
    ],
    "Purchase Agreement": [
        r"purchase agreement",
        r"\bpurchaser\b",
        r"\bseller\b",
        r"purchase price",
    ],
    "Sale Deed": [
        r"sale deed",
        r"\bvendor\b",
        r"consideration amount",
        r"registered sale deed",
    ],
    "Vendor Agreement": [
        r"vendor agreement",
        r"\bvendor\b",
        r"\bsupplier\b",
        r"purchase order",
    ],
    "Memorandum of Understanding (MoU)": [
        r"memorandum of understanding",
        r"\bmou\b",
        r"mutual understanding",
    ],
    "FIR": [
        r"first information report",
        r"\bfir no\b",
        r"police station",
        r"\bipc\b",
        r"\bcomplainant\b",
        r"\baccused\b",
    ],
    "Legal Notice": [
        r"legal notice",
        r"hereby called upon",
        r"\badvocate\b",
        r"take notice that",
    ],
    "Affidavit": [
        r"\baffidavit\b",
        r"solemnly affirm",
        r"\bdeponent\b",
        r"sworn statement",
    ],
    "Court Order": [
        r"in the high court",
        r"supreme court",
        r"\bpetitioner\b",
        r"\brespondent\b",
        r"honou?rable court",
    ],
    "Partnership Agreement": [
        r"partnership agreement",
        r"\bpartners?\b",
        r"profit[- ]sharing",
        r"partnership firm",
    ],
    "Loan Agreement": [
        r"loan agreement",
        r"\blender\b",
        r"\bborrower\b",
        r"\brepayment\b",
        r"principal amount",
    ],
    "Privacy Policy": [
        r"privacy policy",
        r"personal (?:data|information)",
        r"data protection",
        r"\bcookies?\b",
    ],
    "Terms & Conditions": [
        r"terms (?:and|&) conditions",
        r"terms of (?:use|service)",
        r"by using this (?:website|service|app)",
    ],
    "Power of Attorney": [
        r"power of attorney",
        r"attorney[- ]in[- ]fact",
        r"do hereby appoint",
    ],
    "Will": [
        r"last will and testament",
        r"\btestator\b",
        r"\bexecutor\b",
        r"\bbequeath\b",
    ],
    "Insurance Policy": [
        r"insurance policy",
        r"\bpolicyholder\b",
        r"\bpremium\b",
        r"sum assured",
    ],
}

_COMPILED_PATTERNS: Dict[str, List["re.Pattern"]] = {
    doc_type: [re.compile(p, re.IGNORECASE) for p in patterns]
    for doc_type, patterns in DOCUMENT_TYPE_PATTERNS.items()
}


def _normalize(text: str) -> str:
    """Lowercases and collapses whitespace so multi-space/newline-broken
    phrases (common in PDF-extracted text) still match phrase patterns."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def _score_all_types(normalized_text: str) -> Dict[str, int]:
    """Shared scoring step behind both classify_document_type() and
    classify_document_type_ranked() — total pattern-match count per type
    on already-normalized text. Kept as one function so the two callers can
    never drift into scoring text differently."""
    return {
        doc_type: sum(len(pattern.findall(normalized_text)) for pattern in patterns)
        for doc_type, patterns in _COMPILED_PATTERNS.items()
    }


def classify_document_type(full_text: str) -> str:
    """Regex/keyword document-type classifier (Stage 2, no LLM, no
    embeddings). Scores every type by its total pattern-match count on the
    normalized text and returns the best match, or UNKNOWN_DOCUMENT_TYPE if
    nothing clears MIN_CONFIDENT_SCORE.

    Unchanged in behavior and return shape from before
    classify_document_type_ranked() existed — agents/orchestrator.py
    depends on this exact plain-string return for the persisted
    document_type field (which flows into Chroma metadata too), so this
    function is deliberately left alone rather than reimplemented on top
    of the ranked version."""
    if not full_text:
        return UNKNOWN_DOCUMENT_TYPE

    normalized = _normalize(full_text)
    scores = _score_all_types(normalized)

    best_type = max(scores, key=scores.get)
    if scores[best_type] < MIN_CONFIDENT_SCORE:
        return UNKNOWN_DOCUMENT_TYPE
    return best_type


class DocumentTypeClassification(BaseModel):
    document_type: str
    confidence: float = Field(description="0-1, see classify_document_type_ranked for how this is computed")
    runner_up: Optional[str] = Field(default=None, description="Second-best-matching type, if any type other than the winner scored > 0")
    scores: Dict[str, int] = Field(default_factory=dict, description="Raw pattern-match count for every registered type")


def _margin_confidence(best_score: int, second_score: int) -> float:
    """(best - second) / (best + second): 1.0 when the runner-up scored
    zero (the winner is completely uncontested), toward 0.0 as the two
    converge (a genuinely ambiguous call between two plausible types)."""
    total = best_score + second_score
    if total == 0:
        return 0.0
    return (best_score - second_score) / total


def _top_two(scores: Dict[str, int]) -> Tuple[Tuple[str, int], Tuple[str, int]]:
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best = ranked[0]
    second = ranked[1] if len(ranked) > 1 else (None, 0)
    return best, second


def classify_document_type_ranked(full_text: str) -> DocumentTypeClassification:
    """Stage 0 of the Authenticity Verification Engine: the same regex
    scoring as classify_document_type(), but keeping what that function
    computes and discards — the runner-up and the margin between it and
    the winner — as an explicit confidence figure downstream factors can
    act on, rather than treating every classification as equally certain.

    confidence = margin_confidence x evidence_confidence(best_score)

    Both factors have to be strong for confidence to be high: a winner
    that's uncontested (margin ~1) but only cleared by a single stray
    keyword match (evidence_confidence(1) = 0.5) still reads as no more
    than a coin flip's worth of trust — the same "count/(count+1)" curve
    used throughout agents/feature_extraction_agent.py for exactly this
    reason, reused here rather than inventing a second formula. A winner
    that's both dominant *and* backed by several independent pattern hits
    approaches 1.0; two types in a near-tie pull confidence toward 0
    regardless of how much total text matched.
    """
    if not full_text:
        return DocumentTypeClassification(document_type=UNKNOWN_DOCUMENT_TYPE, confidence=0.0)

    normalized = _normalize(full_text)
    scores = _score_all_types(normalized)
    (best_type, best_score), (second_type, second_score) = _top_two(scores)

    if best_score < MIN_CONFIDENT_SCORE:
        return DocumentTypeClassification(document_type=UNKNOWN_DOCUMENT_TYPE, confidence=0.0, scores=scores)

    confidence = _margin_confidence(best_score, second_score) * evidence_confidence(best_score)
    return DocumentTypeClassification(
        document_type=best_type,
        confidence=round(confidence, 4),
        runner_up=second_type if second_score > 0 else None,
        scores=scores,
    )
