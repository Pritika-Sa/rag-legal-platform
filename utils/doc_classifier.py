"""Document-level (not clause-level) language detection, run once per
document on the full concatenated text — never per-chunk, since legal
documents are effectively single-language and `langdetect` is unreliable on
short text — and threaded onto every chunk's Chroma/Mongo metadata by the
caller. Document type detection lives in services/document_classifier.py.
"""

from langdetect import LangDetectException, detect

_LANGDETECT_SAMPLE_CHARS = 2000


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
