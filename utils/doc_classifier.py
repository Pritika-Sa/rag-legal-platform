"""Document-level (not clause-level) classification helpers: language and
contract type. Both run once per document on the full concatenated text —
never per-chunk, since legal documents are effectively single-language and
`langdetect` is unreliable on short text — and the results are threaded
onto every chunk's Chroma/Mongo metadata by the caller.
"""

from langdetect import LangDetectException, detect

_LANGDETECT_SAMPLE_CHARS = 2000

DOCUMENT_TYPE_KEYWORDS = {
    "NDA": ["non-disclosure", "confidential information", "receiving party", "disclosing party", "proprietary information"],
    "Employment Agreement": ["employee", "employer", "salary", "compensation", "at-will", "job title", "benefits"],
    "Lease Agreement": ["lessor", "lessee", "landlord", "tenant", "premises", "rent", "leasehold"],
    "Service Agreement": ["service provider", "scope of work", "deliverables", "statement of work", "service level"],
    "Purchase Agreement": ["purchaser", "seller", "goods", "purchase price", "delivery", "warranty of title"],
}

DEFAULT_DOCUMENT_TYPE = "General Contract"


def detect_language(full_text: str) -> str:
    """Runs langdetect once per document on a leading sample of the text.
    Always returns a non-None string ("unknown" on failure) since Chroma
    metadata cannot hold None."""
    sample = full_text[:_LANGDETECT_SAMPLE_CHARS].strip()
    if not sample:
        return "unknown"
    try:
        return detect(sample)
    except LangDetectException:
        return "unknown"


def detect_document_type(full_text: str) -> str:
    """Keyword-frequency heuristic over the whole document: counts (not just
    presence) so a document mentioning "tenant" repeatedly outweighs one
    incidental mention of an unrelated term. Falls back to a generic label
    if nothing scores above zero."""
    text_lower = full_text.lower()
    scores = {
        dtype: sum(text_lower.count(kw) for kw in keywords)
        for dtype, keywords in DOCUMENT_TYPE_KEYWORDS.items()
    }
    best_type = max(scores, key=scores.get) if scores else DEFAULT_DOCUMENT_TYPE
    return best_type if scores.get(best_type, 0) > 0 else DEFAULT_DOCUMENT_TYPE
