"""Factor 6 of the Authenticity Verification Engine: Metadata Validation.
Wires the already-written but previously dormant
agents.parser_agent.extract_pdf_metadata / extract_docx_metadata into a
scoring factor for the first time — both functions existed in the codebase
well before this redesign but were only reachable via
parse_document_to_json, which nothing in the live orchestrator pipeline
calls (agents/orchestrator.py uses parse_document / parse_document_pages
instead). This factor is largely just giving that dormant extraction code
somewhere to feed.

The only check this factor scores is a hard, logically-defensible one:
does the file's own modification timestamp fall on or after its creation
timestamp? (modified < created is not something normal document-authoring
software can produce on its own.) Deliberately does NOT attempt to compare
the file's technical timestamps against dates mentioned in the document
text — this application's own primary use case is digitizing/uploading
documents long after they were originally signed (scanned paper contracts,
archived agreements), so a "file created suspiciously long after its
claimed document date" check would misfire constantly against completely
legitimate uploads. It also does NOT flag specific "suspicious" authoring
tools (e.g. online PDF converters) — a blacklist like that would be easily
gamed and would falsely accuse many legitimate workflows, the same
overselling risk agents/authenticity_agent.py's fake-address check already
avoids by staying a warning, never a score.

How much metadata was populated at all (author, title, producer, ...)
feeds this factor's *confidence*, not its score — a document with no
author/producer metadata isn't more likely to be fake (plenty of genuine
PDFs are metadata-sparse), it just gives this factor less to reason from.
"""

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agents.parser_agent import extract_docx_metadata, extract_pdf_metadata
from utils.confidence import evidence_confidence

_IGNORED_KEYS = {"error", "page_count", "file_size_bytes", "file_type"}
_SENTINEL_VALUES = {"unknown", "none", ""}

_PDF_DATE_RE = re.compile(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?")


class MetadataValidationFactorResult(BaseModel):
    applicable: bool = Field(description="False for non-PDF/DOCX sources or failed metadata extraction")
    score: float = Field(description="1.0 if modified >= created (or not checkable), 0.0 if modified < created")
    confidence: float = Field(description="0-100. 0 when the date-order check wasn't checkable.")
    created: Optional[str] = None
    modified: Optional[str] = None
    populated_fields: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)


def _not_applicable(reason: str) -> MetadataValidationFactorResult:
    return MetadataValidationFactorResult(applicable=False, score=0.0, confidence=0.0, evidence=[reason])


def _parse_pdf_date(raw: Any) -> Optional[datetime]:
    if not isinstance(raw, str):
        return None
    match = _PDF_DATE_RE.match(raw)
    if not match:
        return None
    year = int(match.group(1))
    month, day, hour, minute, second = (int(g) if g else d for g, d in zip(match.groups()[1:], (1, 1, 0, 0, 0)))
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def _parse_iso_date(raw: Any) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def assess_metadata_validation(file_path: Optional[str]) -> MetadataValidationFactorResult:
    ext = os.path.splitext(file_path or "")[1].lower()
    if ext not in (".pdf", ".docx"):
        return _not_applicable("Metadata validation only applies to PDF/DOCX sources.")
    if not os.path.exists(file_path):
        return _not_applicable(f"File not found at '{file_path}'; could not extract metadata.")

    metadata = extract_pdf_metadata(file_path) if ext == ".pdf" else extract_docx_metadata(file_path)
    if metadata.get("error"):
        return _not_applicable(f"Metadata could not be extracted: {metadata['error']}")

    if ext == ".pdf":
        created = _parse_pdf_date(metadata.get("creationdate"))
        modified = _parse_pdf_date(metadata.get("moddate"))
    else:
        created = _parse_iso_date(metadata.get("created"))
        modified = _parse_iso_date(metadata.get("modified"))

    populated_fields = sorted(
        k for k, v in metadata.items()
        if k not in _IGNORED_KEYS and str(v).strip().lower() not in _SENTINEL_VALUES
    )

    if created and modified:
        consistent = modified >= created
        score = 1.0 if consistent else 0.0
        confidence = round(100.0 * evidence_confidence(len(populated_fields)), 2)
        evidence = [
            f"Creation timestamp: {created.isoformat()}; modification timestamp: {modified.isoformat()}.",
            "CONSISTENT: modification is on or after creation." if consistent
            else "INCONSISTENT: modification timestamp is earlier than the creation timestamp.",
        ]
    else:
        score = 1.0
        confidence = 0.0
        evidence = [
            "Creation and/or modification timestamps were not both available; "
            "date-order consistency could not be checked."
        ]

    evidence.append(f"{len(populated_fields)} metadata field(s) populated: {populated_fields}.")

    return MetadataValidationFactorResult(
        applicable=True, score=score, confidence=confidence,
        created=created.isoformat() if created else None,
        modified=modified.isoformat() if modified else None,
        populated_fields=populated_fields, evidence=evidence,
    )
