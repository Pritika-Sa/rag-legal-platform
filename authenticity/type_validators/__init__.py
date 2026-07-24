"""Document-type-specific validator layer — an ADDITIVE 8th factor on top
of the existing 7-factor Document Authenticity Index (see authenticity/),
not a replacement for it and not a redesign of it. The existing 7 factors
are deliberately generic (structure/clause/cross-field templates keyed by
document type, but the CHECK MACHINERY itself is identical for every
type); this layer instead adds genuinely type-specific evidence — an
Insurance Policy's GST arithmetic or IRDAI registration number has no
equivalent in a Lease Agreement or an Identity Document, so each document
type gets its own purpose-built validator module.

Registered here by document_type string (matching
services.document_classifier's DOCUMENT_TYPE_PATTERNS keys). A type with
no registered validator — Employment Contract, Lease Agreement, Invoice,
Identity Document, and every other type today — reports applicable=False
("no type-specific validator built yet"), never a penalty, so adding one
later is a pure addition to _VALIDATORS below, not a change to this
dispatcher, to authenticity/dai.py, or to agents/authenticity_agent.py.
"""

import logging
from typing import Any, Dict, List, Optional

from authenticity.type_validators.base import DocumentValidatorFactorResult, _not_applicable
from authenticity.type_validators.insurance_policy import assess_insurance_policy

logger = logging.getLogger(__name__)

_VALIDATORS = {
    "Insurance Policy": assess_insurance_policy,
}


def assess_document_type_validators(
    document_type: str,
    full_text: str,
    pages: Optional[List[Dict[str, Any]]] = None,
    clauses: Optional[List[Dict[str, Any]]] = None,
    digital_result: Any = None,
) -> DocumentValidatorFactorResult:
    validator = _VALIDATORS.get(document_type)
    if validator is None:
        logger.debug(f"[type_validators] no validator registered for document_type={document_type!r}")
        return _not_applicable(
            document_type,
            f"No document-type-specific validator is registered for '{document_type}' yet "
            f"(registered: {sorted(_VALIDATORS)}); this factor does not apply to this document.",
        )
    return validator(full_text=full_text, pages=pages, clauses=clauses, digital_result=digital_result)
