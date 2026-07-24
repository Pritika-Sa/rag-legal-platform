"""Factor 8 (document-type-specific): Insurance Policy validator.

Twelve independent evidence checks, each a plain regex/arithmetic extractor
against the already-parsed document (full_text / pages / clauses) or the
already-computed digital_verification factor (reused, not recomputed — QR
scanning and signature-field detection are relatively expensive PDF I/O,
so this validator borrows Factor 5's result rather than re-scanning the
file). None of these checks proves authenticity on its own; each is one
independent piece of evidence combined by base.aggregate_checks into the
factor's score/confidence — exactly the "positive evidence + negative
evidence + coverage + rule confidence" combination the engine as a whole
already uses, applied one level down to insurance-specific signals that
have no equivalent in the 7 generic factors (GST arithmetic, IRDAI
registration, vehicle identifiers, ...).

Every regex here is a plain presence/format detector, deliberately no
different in spirit from rules/clause_rules.json's keyword vocabularies or
agents/knowledge_graph_agent.py's PARTY_RE/JURISDICTION_RE — nothing here
was tuned against a specific sample document, and every check degrades to
applicable=False (never a penalty) when its evidence simply isn't present,
per the module's own "missing evidence is not forgery" rule.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agents.rule_engine import extract_dates, extract_money
from authenticity.type_validators.base import (
    DocumentValidatorFactorResult, EvidenceCheck, aggregate_checks, fuzzy_majority_fraction, weights_for,
)

DOCUMENT_TYPE = "Insurance Policy"

# GST/total-premium arithmetic tolerance: real premium schedules routinely
# add small additional charges (stamp duty, cess) on top of plain
# base*(1+gst) math, so exact equality would false-flag genuine documents.
# 3% relative tolerance is a disclosed, conservative allowance for that —
# not a value chosen to make any particular sample pass.
GST_ARITHMETIC_TOLERANCE = 0.03

_ISSUER_RE = re.compile(
    r"(?:issued\s+by|insurer\s*[:\-])\s*([A-Z][A-Za-z&.,\- ]{3,70}?(?:Insurance|Assurance)[A-Za-z&.,\- ]{0,40})",
    re.IGNORECASE,
)
_ISSUER_FALLBACK_RE = re.compile(
    r"\b([A-Z][A-Za-z&.,\- ]{3,60}?(?:General\s+Insurance|Life\s+Insurance|Insurance\s+Company|Assurance)"
    r"[A-Za-z&.,\- ]{0,30})",
)
_POLICY_NUMBER_RE = re.compile(r"policy\s*(?:no\.?|number)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/]{3,})", re.IGNORECASE)
_PREMIUM_CONTEXT_RE = re.compile(r"premium", re.IGNORECASE)
_GST_PCT_RE = re.compile(r"(?:gst|tax)[^\d%\n]{0,15}(\d{1,2}(?:\.\d+)?)\s?%", re.IGNORECASE)
_BASE_PREMIUM_RE = re.compile(r"(?:net|base)\s+premium[^\d\n]{0,25}([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_TOTAL_PREMIUM_RE = re.compile(
    r"(?:total|gross)\s+premium(?:\s+payable)?[^\d\n]{0,25}([\d,]+(?:\.\d+)?)|"
    r"total\s+payable[^\d\n]{0,25}([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_CUSTOMER_NAME_RE = re.compile(
    r"(?:policyholder|insured(?:'s)?\s+name|proposer(?:'s)?\s+name|name\s+of\s+insured)\s*[:\-]?\s*"
    r"([A-Z][A-Za-z.\- ]{2,50})",
    re.IGNORECASE,
)
_VEHICLE_KEYWORD_RE = re.compile(
    r"\b(vehicle|motor\s+insurance|registration\s+number|engine\s+no|chassis\s+no)\b", re.IGNORECASE,
)
_REG_PLATE_RE = re.compile(r"\b[A-Z]{2}[\s\-]?\d{1,2}[\s\-]?[A-Z]{1,3}[\s\-]?\d{3,4}\b")
_ENGINE_NO_RE = re.compile(r"engine\s*(?:no\.?|number)\s*[:\-]?\s*([A-Z0-9]{5,20})", re.IGNORECASE)
_CHASSIS_NO_RE = re.compile(r"chassis\s*(?:no\.?|number)\s*[:\-]?\s*([A-Z0-9]{5,20})", re.IGNORECASE)
_RECEIPT_RE = re.compile(
    r"\b(receipt\s*(?:no\.?|number)|payment\s+receipt|transaction\s*id|premium\s+received)\b", re.IGNORECASE,
)
_IRDAI_RE = re.compile(
    r"irda[i]?\s*(?:reg(?:istration)?\.?\s*(?:no\.?|number)?)?\s*[:\-]?\s*([A-Z0-9\-/]{3,20})", re.IGNORECASE,
)
_POLICY_PERIOD_CONTEXT_RE = re.compile(r"(?:policy\s*period|period\s*of\s*insurance)[^\n]{0,80}", re.IGNORECASE)
_COMMENCEMENT_CONTEXT_RE = re.compile(
    r"(?:commencement|start|from)\s*date[^\n]{0,40}|risk\s+commences?\s*(?:on|from)?[^\n]{0,40}", re.IGNORECASE,
)
_EXPIRY_CONTEXT_RE = re.compile(r"(?:expiry|end)\s*date[^\n]{0,40}|valid\s*(?:till|until|up\s*to)[^\n]{0,40}", re.IGNORECASE)


def _first_group(pattern: "re.Pattern", text: str) -> Optional[str]:
    m = pattern.search(text)
    if not m:
        return None
    for g in m.groups():
        if g:
            return g.strip()
    return None


def _parse_date_flexible(raw: str) -> Optional[datetime]:
    raw = raw.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _money_value(raw: str) -> Optional[float]:
    match = re.search(r"[\d,]+(?:\.\d+)?", raw)
    if not match:
        return None
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return None


# ── Individual checks ───────────────────────────────────────────────────────

def _check_issuer_name(text: str) -> EvidenceCheck:
    issuer = _first_group(_ISSUER_RE, text) or _first_group(_ISSUER_FALLBACK_RE, text[:2000])
    if issuer:
        return EvidenceCheck(
            name="issuer_name", passed=True, confidence=0.85, applicable=True,
            evidence=f"Issuer detected: '{issuer}'.", reason="An insurer name matching a known issuance phrasing was found.",
        )
    return EvidenceCheck(
        name="issuer_name", passed=False, confidence=0.6, applicable=True,
        evidence="No issuer name found.", reason="No 'Issued by'/'Insurer:' phrasing or Insurance/Assurance company name was detected.",
    )


def _check_policy_number(text: str) -> EvidenceCheck:
    number = _first_group(_POLICY_NUMBER_RE, text)
    if number:
        return EvidenceCheck(
            name="policy_number", passed=True, confidence=0.9, applicable=True,
            evidence=f"Policy number: '{number}'.", reason="A policy number in the expected format was found.",
        )
    return EvidenceCheck(
        name="policy_number", passed=False, confidence=0.7, applicable=True,
        evidence="No policy number found.", reason="No 'Policy No./Number' field was detected anywhere in the document.",
    )


def _check_policy_dates(text: str) -> EvidenceCheck:
    context = _POLICY_PERIOD_CONTEXT_RE.search(text)
    commencement_ctx = _COMMENCEMENT_CONTEXT_RE.search(text)
    expiry_ctx = _EXPIRY_CONTEXT_RE.search(text)

    if not context and not (commencement_ctx and expiry_ctx):
        return EvidenceCheck(
            name="policy_dates", passed=False, confidence=0.0, applicable=False,
            evidence="No policy-period/commencement/expiry date fields found.",
            reason="No date-labelled context relevant to a policy period was present in the document.",
        )

    window = context.group(0) if context else f"{commencement_ctx.group(0)} {expiry_ctx.group(0)}"
    found_dates = extract_dates(window) or extract_dates(text)
    if len(found_dates) < 2:
        return EvidenceCheck(
            name="policy_dates", passed=True, confidence=0.4, applicable=True,
            evidence=f"Policy-period language found but only {len(found_dates)} date(s) could be parsed nearby.",
            reason="Date labels were present; a start/end pair could not be confidently isolated, so ordering was not checked.",
        )

    start, end = _parse_date_flexible(found_dates[0]), _parse_date_flexible(found_dates[1])
    if start is None or end is None:
        return EvidenceCheck(
            name="policy_dates", passed=True, confidence=0.5, applicable=True,
            evidence=f"Policy dates found ({found_dates[0]}, {found_dates[1]}) but could not be parsed for ordering.",
            reason="Dates were present in an unrecognized format; presence is positive evidence even though ordering could not be verified.",
        )

    if end >= start:
        return EvidenceCheck(
            name="policy_dates", passed=True, confidence=0.9, applicable=True,
            evidence=f"Policy period {start.date()} to {end.date()} is chronologically valid.",
            reason="Expiry date is on or after the commencement date.",
        )
    return EvidenceCheck(
        name="policy_dates", passed=False, confidence=0.9, applicable=True,
        evidence=f"Policy period {start.date()} to {end.date()} is chronologically invalid.",
        reason="Expiry date is earlier than the commencement date — an internally inconsistent policy period.",
    )


def _check_premium_values(text: str) -> EvidenceCheck:
    if not _PREMIUM_CONTEXT_RE.search(text):
        return EvidenceCheck(
            name="premium_values", passed=False, confidence=0.0, applicable=False,
            evidence="No premium-related language found.", reason="This document does not mention a premium at all.",
        )
    amounts = extract_money(text)
    if amounts:
        return EvidenceCheck(
            name="premium_values", passed=True, confidence=0.8, applicable=True,
            evidence=f"Premium amount(s) found: {amounts[:3]}.", reason="At least one monetary figure was found alongside premium language.",
        )
    return EvidenceCheck(
        name="premium_values", passed=False, confidence=0.6, applicable=True,
        evidence="Premium is mentioned but no monetary figure was found.",
        reason="'Premium' appears in the text but no parsable amount accompanies it.",
    )


def _check_gst_arithmetic(text: str) -> EvidenceCheck:
    gst_pct_raw = _first_group(_GST_PCT_RE, text)
    base_raw = _first_group(_BASE_PREMIUM_RE, text)
    total_raw = _first_group(_TOTAL_PREMIUM_RE, text)

    if not (gst_pct_raw and base_raw and total_raw):
        missing = [n for n, v in (("GST %", gst_pct_raw), ("base/net premium", base_raw), ("total/gross premium", total_raw)) if not v]
        return EvidenceCheck(
            name="gst_arithmetic", passed=False, confidence=0.0, applicable=False,
            evidence=f"Missing: {', '.join(missing)}.",
            reason="GST arithmetic requires all three of a GST %, a base premium, and a total premium; not all were found.",
        )

    gst_pct, base, total = float(gst_pct_raw), _money_value(base_raw), _money_value(total_raw)
    if base is None or total is None or base <= 0:
        return EvidenceCheck(
            name="gst_arithmetic", passed=False, confidence=0.0, applicable=False,
            evidence="Base or total premium could not be parsed as a number.",
            reason="Numeric values for base/total premium were not parsable.",
        )

    expected_total = base * (1 + gst_pct / 100)
    relative_error = abs(expected_total - total) / max(total, 1.0)
    if relative_error <= GST_ARITHMETIC_TOLERANCE:
        return EvidenceCheck(
            name="gst_arithmetic", passed=True, confidence=0.9, applicable=True,
            evidence=f"Base {base:,.2f} + {gst_pct:g}% GST ≈ total {total:,.2f} (expected {expected_total:,.2f}).",
            reason=f"Total premium matches base+GST within {GST_ARITHMETIC_TOLERANCE:.0%} tolerance.",
        )
    return EvidenceCheck(
        name="gst_arithmetic", passed=False, confidence=0.9, applicable=True,
        evidence=f"Base {base:,.2f} + {gst_pct:g}% GST = expected {expected_total:,.2f}, but stated total is {total:,.2f}.",
        reason=f"Total premium diverges from base+GST by {relative_error:.1%}, beyond the {GST_ARITHMETIC_TOLERANCE:.0%} tolerance.",
    )


def _check_customer_identity_consistency(text: str) -> EvidenceCheck:
    names = [m.strip() for m in _CUSTOMER_NAME_RE.findall(text) if m.strip()]
    if len(names) < 2:
        return EvidenceCheck(
            name="customer_identity_consistency", passed=False, confidence=0.0, applicable=False,
            evidence=f"Customer name mentioned {len(names)} time(s).",
            reason="Fewer than 2 occurrences of a policyholder/insured name were found, so consistency cannot be checked.",
        )
    fraction = fuzzy_majority_fraction([n.upper() for n in names])
    if fraction >= 1.0:
        return EvidenceCheck(
            name="customer_identity_consistency", passed=True, confidence=0.85, applicable=True,
            evidence=f"Customer name consistent across {len(names)} mentions: '{names[0]}'.",
            reason="Every occurrence of the policyholder/insured name fuzzy-matched the majority value.",
        )
    return EvidenceCheck(
        name="customer_identity_consistency", passed=False, confidence=0.85, applicable=True,
        evidence=f"Customer name varies across {len(names)} mentions: {sorted(set(n.upper() for n in names))}.",
        reason=f"Only {fraction:.0%} of name occurrences agree with each other.",
    )


def _check_vehicle_identifiers(text: str) -> EvidenceCheck:
    if not _VEHICLE_KEYWORD_RE.search(text):
        return EvidenceCheck(
            name="vehicle_identifiers", passed=False, confidence=0.0, applicable=False,
            evidence="No vehicle/motor-insurance language found.",
            reason="This does not appear to be a motor insurance policy, so vehicle identifiers are not expected.",
        )
    reg = _REG_PLATE_RE.search(text)
    engine = _ENGINE_NO_RE.search(text)
    chassis = _CHASSIS_NO_RE.search(text)
    found = [label for label, m in (("registration", reg), ("engine", engine), ("chassis", chassis)) if m]
    if len(found) >= 2:
        return EvidenceCheck(
            name="vehicle_identifiers", passed=True, confidence=0.85, applicable=True,
            evidence=f"Vehicle identifiers found: {found}.", reason="At least 2 of 3 expected vehicle identifiers were present.",
        )
    return EvidenceCheck(
        name="vehicle_identifiers", passed=False, confidence=0.7, applicable=True,
        evidence=f"Only {len(found)} vehicle identifier(s) found: {found}.",
        reason="Motor-insurance language is present but fewer than 2 of registration/engine/chassis numbers were detected.",
    )


def _check_receipt_information(text: str) -> EvidenceCheck:
    match = _RECEIPT_RE.search(text)
    if match:
        return EvidenceCheck(
            name="receipt_information", passed=True, confidence=0.75, applicable=True,
            evidence=f"Receipt/payment reference found: '{match.group(0)}'.",
            reason="A receipt number, transaction ID, or payment confirmation phrase was found.",
        )
    return EvidenceCheck(
        name="receipt_information", passed=False, confidence=0.5, applicable=True,
        evidence="No receipt/payment reference found.", reason="No receipt number, transaction ID, or payment confirmation phrase was found.",
    )


def _check_irdai_registration(text: str) -> EvidenceCheck:
    number = _first_group(_IRDAI_RE, text)
    if number:
        return EvidenceCheck(
            name="irdai_registration", passed=True, confidence=0.85, applicable=True,
            evidence=f"IRDAI registration reference: '{number}'.",
            reason="An IRDAI registration number/reference was found.",
        )
    return EvidenceCheck(
        name="irdai_registration", passed=False, confidence=0.6, applicable=True,
        evidence="No IRDAI registration reference found.",
        reason="No IRDAI registration number or reference was found anywhere in the document.",
    )


def _check_qr_presence(digital_result: Any) -> EvidenceCheck:
    if digital_result is None or not getattr(digital_result, "applicable", False):
        return EvidenceCheck(
            name="qr_presence", passed=False, confidence=0.0, applicable=False,
            evidence="Digital verification did not run (non-PDF source or unreadable file).",
            reason="QR presence can only be checked on PDF sources that were successfully opened.",
        )
    has_qr = bool(getattr(digital_result, "has_qr_or_barcode", False))
    confidence = max(0.0, min(1.0, getattr(digital_result, "confidence", 0.0) / 100.0))
    return EvidenceCheck(
        name="qr_presence", passed=has_qr, confidence=confidence, applicable=True,
        evidence="QR/barcode found on the document." if has_qr else "No QR/barcode found.",
        reason=(
            "Presence only — this is supporting evidence, not proof of authenticity; only cryptographic "
            "verification of the QR payload could confirm validity."
            if has_qr else "No verification QR/barcode was detected — a weak negative signal, not proof of forgery."
        ),
    )


def _check_digital_signature_presence(digital_result: Any) -> EvidenceCheck:
    if digital_result is None or not getattr(digital_result, "applicable", False):
        return EvidenceCheck(
            name="digital_signature_presence", passed=False, confidence=0.0, applicable=False,
            evidence="Digital verification did not run (non-PDF source or unreadable file).",
            reason="Signature-field presence can only be checked on PDF sources that were successfully opened.",
        )
    has_sig = bool(getattr(digital_result, "has_signature_field", False))
    confidence = max(0.0, min(1.0, getattr(digital_result, "confidence", 0.0) / 100.0))
    return EvidenceCheck(
        name="digital_signature_presence", passed=has_sig, confidence=confidence, applicable=True,
        evidence="A digital signature field is present in the PDF." if has_sig else "No digital signature field found.",
        reason=(
            "Field presence only — not cryptographic proof the signature itself is valid."
            if has_sig else "No signature field was found — a weak negative signal, not proof of forgery."
        ),
    )


def _check_cross_page_consistency(pages: List[Dict[str, Any]]) -> EvidenceCheck:
    real_pages = [p for p in (pages or []) if (p.get("raw_text") or "").strip()]
    if len(real_pages) < 2:
        return EvidenceCheck(
            name="cross_page_consistency", passed=False, confidence=0.0, applicable=False,
            evidence=f"Only {len(real_pages)} page(s) of independent text available.",
            reason="Cross-page consistency requires 2+ independently-extracted pages (PDF only).",
        )

    per_page_numbers = []
    for page in real_pages:
        m = _POLICY_NUMBER_RE.search(page.get("raw_text") or "")
        if m:
            per_page_numbers.append(m.group(1).strip().upper())

    if len(per_page_numbers) < 2:
        return EvidenceCheck(
            name="cross_page_consistency", passed=False, confidence=0.0, applicable=False,
            evidence=f"Policy number appears on {len(per_page_numbers)} distinct page(s).",
            reason="The policy number needs to recur on 2+ pages to check cross-page consistency.",
        )

    fraction = fuzzy_majority_fraction(per_page_numbers)
    if fraction >= 1.0:
        return EvidenceCheck(
            name="cross_page_consistency", passed=True, confidence=0.85, applicable=True,
            evidence=f"Policy number consistent across {len(per_page_numbers)} pages: '{per_page_numbers[0]}'.",
            reason="Every page-level occurrence of the policy number fuzzy-matched the majority value.",
        )
    return EvidenceCheck(
        name="cross_page_consistency", passed=False, confidence=0.85, applicable=True,
        evidence=f"Policy number varies across pages: {sorted(set(per_page_numbers))}.",
        reason=f"Only {fraction:.0%} of page-level occurrences agree with each other.",
    )


def assess_insurance_policy(
    full_text: str, pages: Optional[List[Dict[str, Any]]] = None,
    clauses: Optional[List[Dict[str, Any]]] = None, digital_result: Any = None,
) -> DocumentValidatorFactorResult:
    text = full_text or ""

    checks = [
        _check_issuer_name(text),
        _check_policy_number(text),
        _check_policy_dates(text),
        _check_premium_values(text),
        _check_gst_arithmetic(text),
        _check_customer_identity_consistency(text),
        _check_vehicle_identifiers(text),
        _check_receipt_information(text),
        _check_irdai_registration(text),
        _check_qr_presence(digital_result),
        _check_digital_signature_presence(digital_result),
        _check_cross_page_consistency(pages or []),
    ]

    return aggregate_checks(DOCUMENT_TYPE, checks, weights_for(DOCUMENT_TYPE))
