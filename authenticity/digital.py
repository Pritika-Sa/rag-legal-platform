"""Factor 5 of the Authenticity Verification Engine: Digital Verification.
Two independent, purely structural checks against the raw PDF file (not
the extracted text the other factors work from):

  1. QR/barcode presence -- pages are rasterized (pdfplumber's built-in
     pypdfium2 backend, no extra system dependency) and scanned with
     pyzbar. Many genuine institutional documents (insurance policies,
     government notices, bank statements) embed a verification QR code;
     its total absence is a weak negative signal, not proof of forgery.
  2. Digital signature field presence -- the PDF's AcroForm is inspected
     via pikepdf for a field of type /Sig.

Deliberately scoped as field/artifact *presence* detection, not
cryptographic signature-chain validation -- pikepdf can tell us a /Sig
field exists, not that any signature it contains is cryptographically
valid, and overselling that distinction would be dishonest (the same
posture agents/authenticity_agent.py already takes with its fake-address
check: a weak heuristic reported as a weak heuristic, never as proof).

Reworked 2026-07-20: scoring used to be `(has_qr + has_sig) / 2`, which
reads as a punishing 50% the moment either artifact is absent -- including
the digital-signature FIELD, a narrow PDF-native property almost no real
document (scanned, flattened, or printed-then-scanned) will ever carry,
even when it is genuinely signed and genuinely authentic. That treated a
near-universal absence as a 50-point penalty rather than the "no evidence
either way" it actually is. Presence of either artifact is now purely
BONUS evidence on top of a neutral baseline; absence of either is never
subtracted -- only cryptographic verification could prove a signature or a
QR payload is genuine, and this factor deliberately never attempts that
(scoped as presence detection only, as above), so its ABSENCE is reported
as "verification unavailable," not "verification failed."
"""

import logging
import os
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from utils.confidence import evidence_confidence

logger = logging.getLogger(__name__)

MAX_PAGES_TO_SCAN = 10

# Neutral baseline when neither artifact is found -- "no positive evidence
# either way," not a penalty. Each artifact found adds a bonus on top;
# finding both reaches 1.0. A single disclosed, ablatable constant, the
# same kind as risk_engine.fusion's shrinkage/concentration constants.
DIGITAL_NEUTRAL_BASELINE = 0.5
DIGITAL_ARTIFACT_BONUS = 0.25  # per artifact found; 2 artifacts -> baseline + 2*bonus == 1.0


class DigitalVerificationFactorResult(BaseModel):
    applicable: bool = Field(description="False for non-PDF sources or files that could not be opened")
    score: float = Field(
        description=f"{DIGITAL_NEUTRAL_BASELINE:.2f} baseline (no artifacts found -- neutral, not penalized) "
                    f"plus {DIGITAL_ARTIFACT_BONUS:.2f} bonus per artifact (QR/barcode, signature field) found, 0-1."
    )
    confidence: float = Field(description="0-100")
    has_qr_or_barcode: bool = False
    has_signature_field: bool = False
    cryptographic_verification: str = Field(
        default="Unavailable",
        description="Always 'Unavailable' -- this factor detects artifact PRESENCE only; only cryptographic "
                    "validation could prove a signature or QR payload genuine, and this engine never attempts "
                    "that, so it is honestly reported as unavailable rather than 'failed.'",
    )
    pages_scanned_for_qr: int = 0
    evidence: List[str] = Field(default_factory=list)


def _not_applicable(reason: str) -> DigitalVerificationFactorResult:
    logger.debug(f"[digital] not applicable: {reason}")
    return DigitalVerificationFactorResult(applicable=False, score=0.0, confidence=0.0, evidence=[reason])


def _scan_for_qr(file_path: str) -> Tuple[bool, int]:
    """Returns (has_qr_or_barcode, pages_scanned). A rasterization/decode
    failure on a given page counts as 'no barcode found on this page', not
    a hard error -- one malformed page must not sink the whole scan."""
    import pdfplumber
    from pyzbar.pyzbar import decode as zbar_decode

    found = False
    scanned = 0
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages[:MAX_PAGES_TO_SCAN]:
            try:
                image = page.to_image(resolution=150).original
                scanned += 1
                if zbar_decode(image):
                    found = True
                    break
            except Exception:
                continue
    return found, scanned


def _has_signature_field(file_path: str) -> bool:
    import pikepdf

    with pikepdf.open(file_path) as pdf:
        acroform = pdf.Root.get("/AcroForm")
        if not acroform:
            return False
        for field in acroform.get("/Fields", []):
            if str(field.get("/FT", "")) == "/Sig":
                return True
        return False


def assess_digital_verification(file_path: Optional[str]) -> DigitalVerificationFactorResult:
    if not file_path or os.path.splitext(file_path)[1].lower() != ".pdf":
        return _not_applicable("Digital verification only applies to PDF sources.")
    if not os.path.exists(file_path):
        return _not_applicable(f"File not found at '{file_path}'; could not check for digital artifacts.")

    qr_error = sig_error = None
    has_qr, pages_scanned = False, 0
    has_sig = False

    try:
        has_qr, pages_scanned = _scan_for_qr(file_path)
    except Exception as exc:
        qr_error = str(exc)

    try:
        has_sig = _has_signature_field(file_path)
    except Exception as exc:
        sig_error = str(exc)

    if qr_error and sig_error:
        return _not_applicable(f"Could not inspect '{file_path}' for digital artifacts: {sig_error}")

    logger.debug(
        f"[digital] raw inputs: has_qr={has_qr} pages_scanned={pages_scanned} qr_error={qr_error!r} "
        f"has_sig={has_sig} sig_error={sig_error!r}"
    )

    # Presence is bonus-only evidence on top of a neutral baseline -- absence
    # of either artifact is never subtracted (see module docstring). A check
    # that errored (qr_error/sig_error set) contributes no bonus but is also
    # not counted as "absence found," since we genuinely don't know either way.
    bonus = 0.0
    if qr_error is None and has_qr:
        bonus += DIGITAL_ARTIFACT_BONUS
    if sig_error is None and has_sig:
        bonus += DIGITAL_ARTIFACT_BONUS
    score = min(1.0, DIGITAL_NEUTRAL_BASELINE + bonus)

    qr_confidence = 100.0 * evidence_confidence(pages_scanned) if qr_error is None else 0.0
    sig_confidence = 100.0 if sig_error is None else 0.0
    confidence = round((qr_confidence + sig_confidence) / 2.0, 2)

    evidence = [
        "Cryptographic verification unavailable: this engine detects artifact presence only -- QR/barcode "
        "and signature-field presence are positive evidence, never proof of authenticity, and their absence "
        "is not treated as a failure.",
        f"QR/barcode scan: {'found (+bonus)' if (has_qr and qr_error is None) else 'none found (neutral, no penalty)'} "
        f"across {pages_scanned} page(s) scanned" + (f" (scan unavailable: {qr_error})" if qr_error else "") + ".",
        f"Signature field: {'present (+bonus)' if (has_sig and sig_error is None) else 'not present (neutral, no penalty)'} "
        f"in the PDF's AcroForm" + (f" (check unavailable: {sig_error})" if sig_error else "") + ".",
    ]

    logger.debug(f"[digital] adaptation=presence-as-bonus final_score={score:.4f} confidence={confidence:.2f}")

    return DigitalVerificationFactorResult(
        applicable=True, score=round(score, 4), confidence=confidence,
        has_qr_or_barcode=has_qr, has_signature_field=has_sig,
        pages_scanned_for_qr=pages_scanned, evidence=evidence,
    )
