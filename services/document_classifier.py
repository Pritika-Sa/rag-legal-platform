"""Document Type Classifier (Stage 2, no LLM, no embeddings): a deterministic
regex/keyword classifier that runs once per document immediately after
parsing. The result is persisted to the documents collection by the caller
(agents/orchestrator.py), so this never needs to run twice for the same
document.

To add a new document type: add an entry to DOCUMENT_TYPE_PATTERNS with a
list of regex strings (case-insensitive, matched against the normalized
text). No other code needs to change.
"""

import re
from typing import Dict, List

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


def classify_document_type(full_text: str) -> str:
    """Regex/keyword document-type classifier (Stage 2, no LLM, no
    embeddings). Scores every type by its total pattern-match count on the
    normalized text and returns the best match, or UNKNOWN_DOCUMENT_TYPE if
    nothing clears MIN_CONFIDENT_SCORE."""
    if not full_text:
        return UNKNOWN_DOCUMENT_TYPE

    normalized = _normalize(full_text)
    scores = {
        doc_type: sum(len(pattern.findall(normalized)) for pattern in patterns)
        for doc_type, patterns in _COMPILED_PATTERNS.items()
    }

    best_type = max(scores, key=scores.get)
    if scores[best_type] < MIN_CONFIDENT_SCORE:
        return UNKNOWN_DOCUMENT_TYPE
    return best_type
