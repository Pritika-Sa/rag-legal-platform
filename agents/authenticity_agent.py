"""Authenticity Detection Agent (Stage 2, no LLM) — deliberately separate
from risk_scoring_agent.py. Legal risk measures how dangerous a clause's
*content* is; authenticity measures whether the document is even a genuine,
complete, well-formed legal document in the first place. A fabricated
document with bland, low-risk-sounding clauses would score "low risk" and
still be fake — the two scores must never be blended.

Every check below is a concrete regex/heuristic with an explicit point
deduction, so results are explainable to an examiner. The fake-address
check is intentionally a warning only, never a scored deduction — regex
cannot verify a real-world address exists, and overselling that capability
would be dishonest.
"""

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agents.knowledge_graph_agent import PARTY_RE
from agents.rule_engine import CLAUSE_RULES, extract_dates, extract_section_refs

_SIGNATURE_RE = re.compile(r"\b(signature|signed|/s/|authorized representative)\b", re.IGNORECASE)
_EXECUTION_RE = re.compile(r"IN\s+WITNESS\s+WHEREOF", re.IGNORECASE)
_WITNESS_RE = re.compile(r"\bwitness(es)?\b", re.IGNORECASE)
_BETWEEN_AND_RE = re.compile(r"\bBETWEEN\b.{0,200}?\bAND\b", re.IGNORECASE | re.DOTALL)
_LEADING_NUM_RE = re.compile(r"^(\d+)(?:\.\d+)*")
_PO_BOX_RE = re.compile(r"P\.?O\.?\s*Box\s*\d+", re.IGNORECASE)
_POSTAL_CODE_RE = re.compile(r"\b\d{5,6}\b")

# document_type values that conventionally require a witness — none of the
# current utils.doc_classifier.DOCUMENT_TYPE_KEYWORDS categories are in this
# set today, so this check is a soft warning in practice until the document
# type taxonomy grows to include witness-requiring instruments.
WITNESS_REQUIRED_TYPES = {"Deed", "Affidavit", "Will"}

MIN_REALISTIC_CHARS = 500

DEDUCTIONS = {
    "missing_signatures": 20,
    "missing_execution_section": 15,
    "missing_witnesses": 10,
    "missing_dates": 15,
    "missing_party_names": 20,
    "broken_numbering": 10,
    "missing_governing_law": 10,
    "unrealistic_formatting": 15,
    "dangling_references": 10,
    "empty_mandatory_clauses": 10,
    "duplicate_clauses": 10,
}


class AuthenticityResult(BaseModel):
    authenticity_score: int = Field(description="0-100, 100 = fully authentic-looking")
    authenticity_level: str = Field(description="'Authentic', 'Suspicious', or 'Highly Suspicious'")
    fraud_indicators: List[str] = Field(default_factory=list, description="Hard findings that reduced the score")
    missing_information: List[str] = Field(default_factory=list, description="Expected content that was not found")
    warnings: List[str] = Field(default_factory=list, description="Soft, low-confidence signals — never scored")


def _tail(full_text: str, fraction: float, min_chars: int = 400) -> str:
    """Last `fraction` of the document, but never less than `min_chars` —
    a pure percentage window is too small for short (or short test) documents
    to reliably catch a closing signature/execution block."""
    if not full_text:
        return ""
    window = max(int(len(full_text) * fraction), min_chars)
    return full_text[-window:]


def _check_signatures(full_text: str) -> bool:
    return bool(_SIGNATURE_RE.search(_tail(full_text, 0.2)))


def _check_execution_section(full_text: str) -> bool:
    return bool(_EXECUTION_RE.search(_tail(full_text, 0.25)))


def _check_party_names(full_text: str) -> bool:
    return bool(PARTY_RE.search(full_text)) or bool(_BETWEEN_AND_RE.search(full_text))


def _check_numbering(raw_sections: List[Dict[str, Any]]) -> bool:
    """Returns True if numbering is broken (decreasing or repeated)."""
    seen = []
    for sec in raw_sections:
        match = _LEADING_NUM_RE.match(sec.get("section_name", "").strip())
        if not match:
            continue
        num = int(match.group(1))
        if seen and (num < seen[-1] or num in seen):
            return True
        seen.append(num)
    return False


def _check_dangling_references(raw_sections: List[Dict[str, Any]], full_text: str) -> bool:
    known_numbers = set()
    for sec in raw_sections:
        match = _LEADING_NUM_RE.match(sec.get("section_name", "").strip())
        if match:
            known_numbers.add(match.group(1))
    for ref in extract_section_refs(full_text):
        ref_num_match = re.search(r"(\d+)", ref)
        if ref_num_match and ref_num_match.group(1) not in known_numbers:
            return True
    return False


def _check_duplicate_clauses(clauses: List[Dict[str, Any]]) -> bool:
    texts = [c.get("text_content", "") for c in clauses if c.get("text_content")]
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if SequenceMatcher(None, texts[i], texts[j]).ratio() > 0.9:
                return True
    return False


def _check_fake_address(full_text: str) -> bool:
    """Low-confidence signal only: a PO-Box-only address with no nearby
    postal-code-shaped token. Regex cannot verify a real-world address
    exists — this is a heuristic warning, not a fraud claim."""
    for match in _PO_BOX_RE.finditer(full_text):
        window = full_text[max(0, match.start() - 60):match.end() + 60]
        if not _POSTAL_CODE_RE.search(window):
            return True
    return False


def assess_document_authenticity(doc_name: str, raw_sections: List[Dict[str, Any]],
                                  clauses: List[Dict[str, Any]], full_text: str,
                                  document_type: Optional[str] = None) -> AuthenticityResult:
    fraud_indicators: List[str] = []
    missing_information: List[str] = []
    warnings: List[str] = []
    deductions_applied = 0

    if not _check_signatures(full_text):
        fraud_indicators.append("No signature block detected near the end of the document.")
        deductions_applied += DEDUCTIONS["missing_signatures"]

    if not _check_execution_section(full_text):
        fraud_indicators.append("No execution section ('IN WITNESS WHEREOF' or equivalent) detected.")
        deductions_applied += DEDUCTIONS["missing_execution_section"]

    if document_type in WITNESS_REQUIRED_TYPES:
        if not _WITNESS_RE.search(full_text):
            fraud_indicators.append(f"Document type '{document_type}' conventionally requires witnesses, none detected.")
            deductions_applied += DEDUCTIONS["missing_witnesses"]
    elif not _WITNESS_RE.search(full_text):
        warnings.append("No witness references found (not necessarily required for this document type).")

    if not extract_dates(full_text):
        fraud_indicators.append("No dates found anywhere in the document.")
        deductions_applied += DEDUCTIONS["missing_dates"]

    if not _check_party_names(full_text):
        fraud_indicators.append("No identifiable party names found (no defined-term or 'BETWEEN...AND' preamble pattern).")
        deductions_applied += DEDUCTIONS["missing_party_names"]

    if _check_numbering(raw_sections):
        fraud_indicators.append("Section numbering is out of order or repeated.")
        deductions_applied += DEDUCTIONS["broken_numbering"]

    jurisdiction_keywords = CLAUSE_RULES.get("Jurisdiction", {}).get("keywords", [])
    if not any(kw in full_text.lower() for kw in jurisdiction_keywords):
        missing_information.append("No governing law / jurisdiction clause detected.")
        deductions_applied += DEDUCTIONS["missing_governing_law"]

    if len(full_text) < MIN_REALISTIC_CHARS or len(raw_sections) <= 1:
        fraud_indicators.append("Document is unrealistically short or shows no real internal structure.")
        deductions_applied += DEDUCTIONS["unrealistic_formatting"]

    if _check_dangling_references(raw_sections, full_text):
        fraud_indicators.append("Contains section references that don't match any section in the document.")
        deductions_applied += DEDUCTIONS["dangling_references"]

    if _check_fake_address(full_text):
        warnings.append("A PO-Box-only address without a nearby postal code was found — a weak, unverified signal, not proof of a fake address.")

    classifications = {c.get("classification") for c in clauses}
    if "Termination" not in classifications and "Jurisdiction" not in classifications:
        missing_information.append("Neither a Termination nor a Jurisdiction clause was found.")
        deductions_applied += DEDUCTIONS["empty_mandatory_clauses"]

    if _check_duplicate_clauses(clauses):
        fraud_indicators.append("Near-duplicate clause text found across two or more clauses.")
        deductions_applied += DEDUCTIONS["duplicate_clauses"]

    authenticity_score = max(0, 100 - deductions_applied)
    if authenticity_score >= 70:
        authenticity_level = "Authentic"
    elif authenticity_score >= 40:
        authenticity_level = "Suspicious"
    else:
        authenticity_level = "Highly Suspicious"

    return AuthenticityResult(
        authenticity_score=authenticity_score,
        authenticity_level=authenticity_level,
        fraud_indicators=fraud_indicators,
        missing_information=missing_information,
        warnings=warnings,
    )
