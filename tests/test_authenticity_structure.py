"""Tests for authenticity/structure.py (Factor 1 of the Authenticity
Verification Engine) — continuous fraction-based structure scoring,
confidence-weighted blending between the type-specific and generic-minimal
templates, and graceful fallback for unrecognized document types.

Run with:  python -m unittest discover -s tests
"""

import unittest

from authenticity.structure import GENERIC_DOCUMENT_AGNOSTIC_KEY, GENERIC_MINIMAL_KEY, assess_structure
from services.document_classifier import (
    UNKNOWN_DOCUMENT_TYPE,
    DocumentTypeClassification,
    classify_document_type_ranked,
)

GOOD_INSURANCE_POLICY = """
INSURANCE POLICY

Policy Number: POL-88213-A
Policyholder: Ramesh Kumar
Sum Assured: Rs. 5,00,000
Premium: Rs. 12,000 per annum
Effective Date: 1st January 2024

Signature: ___________
Authorized Signatory
"""

AMBIGUOUS_TEXT = "The lessor and lessee agree the landlord and tenant terms herein, dated 2024, signed below."

UNRELATED_TEXT = "The quick brown fox jumps over the lazy dog near the river bank."


class HighConfidenceTemplateTests(unittest.TestCase):
    def test_well_formed_document_scores_high(self):
        classification = classify_document_type_ranked(GOOD_INSURANCE_POLICY)
        self.assertEqual(classification.document_type, "Insurance Policy")
        result = assess_structure(GOOD_INSURANCE_POLICY, classification)
        self.assertEqual(result.template_used, "Insurance Policy")
        self.assertEqual(result.missing_sections, [])
        self.assertGreater(result.score, 0.9)

    def test_one_missing_section_is_a_proportional_hit_not_catastrophic(self):
        # Regression test for the exact failure mode this factor exists to
        # fix: one missing section out of seven must not tank the score
        # the way a flat -20 deduction would.
        text_missing_policy_number = GOOD_INSURANCE_POLICY.replace("Policy Number: POL-88213-A\n", "")
        classification = classify_document_type_ranked(text_missing_policy_number)
        result = assess_structure(text_missing_policy_number, classification)
        self.assertIn("Policy Number", result.missing_sections)
        self.assertGreater(result.score, 0.6)   # still clearly "mostly complete", not tanked
        self.assertLess(result.score, 0.95)     # but visibly lower than the fully-complete case

    def test_evidence_lists_found_and_missing_sections(self):
        classification = classify_document_type_ranked(GOOD_INSURANCE_POLICY)
        result = assess_structure(GOOD_INSURANCE_POLICY, classification)
        joined = " ".join(result.evidence)
        self.assertIn("Found: Policy Number", joined)


class ScoreConfidenceDecouplingTests(unittest.TestCase):
    # Reworked 2026-07-20: classification confidence used to blend the
    # SCORE toward the generic template as confidence dropped -- a
    # perfectly-structured Insurance Policy would score lower purely
    # because the type classifier itself was uncertain, conflating "what
    # type is this" with "is it well organized." The score is now the
    # type-specific template's own fraction at full weight whenever a
    # template is registered, regardless of classification confidence;
    # only CONFIDENCE (not score) still reflects classification confidence.
    def test_low_confidence_classification_does_not_lower_the_structure_score(self):
        from authenticity.structure import _check_template, _fraction, _normalize
        normalized = _normalize(GOOD_INSURANCE_POLICY)
        type_found, type_missing = _check_template(normalized, "Insurance Policy")
        type_score = _fraction(type_found, type_missing)

        low_confidence = DocumentTypeClassification(document_type="Insurance Policy", confidence=0.1)
        high_confidence = DocumentTypeClassification(document_type="Insurance Policy", confidence=0.95)

        low_result = assess_structure(GOOD_INSURANCE_POLICY, low_confidence)
        high_result = assess_structure(GOOD_INSURANCE_POLICY, high_confidence)

        # Same score either way -- the score is the type-specific template's
        # own fraction, independent of how confident the classification was.
        self.assertAlmostEqual(low_result.score, type_score, places=4)
        self.assertAlmostEqual(high_result.score, type_score, places=4)
        self.assertAlmostEqual(low_result.score, high_result.score, places=4)

    def test_classification_confidence_still_moves_confidence_not_score(self):
        low_confidence = DocumentTypeClassification(document_type="Insurance Policy", confidence=0.1)
        high_confidence = DocumentTypeClassification(document_type="Insurance Policy", confidence=0.95)
        low_result = assess_structure(GOOD_INSURANCE_POLICY, low_confidence)
        high_result = assess_structure(GOOD_INSURANCE_POLICY, high_confidence)

        self.assertAlmostEqual(low_result.score, high_result.score, places=4)
        self.assertLess(low_result.confidence, high_result.confidence)

    def test_evidence_explains_the_decoupling(self):
        classification = DocumentTypeClassification(document_type="Insurance Policy", confidence=0.3)
        result = assess_structure(GOOD_INSURANCE_POLICY, classification)
        joined = " ".join(result.evidence)
        self.assertIn("not the structure score itself", joined)


class NoTemplateFallbackTests(unittest.TestCase):
    def test_unknown_document_type_falls_back_to_document_agnostic_not_contract_template(self):
        # 2026-07-26 audit follow-up: a genuinely Unknown document must no
        # longer be scored against the contract-shaped generic_minimal
        # template (Title=agreement/policy/contract/deed, Parties="between
        # X and Y", Signature="in witness whereof") -- a genuine invoice,
        # receipt, or ID legitimately has none of that language, which is
        # exactly what caused every unrecognized document type to score
        # "Likely Manipulated or Forged" regardless of genuineness.
        classification = classify_document_type_ranked(UNRELATED_TEXT)
        result = assess_structure(UNRELATED_TEXT, classification)
        self.assertEqual(result.template_used, GENERIC_DOCUMENT_AGNOSTIC_KEY)
        self.assertAlmostEqual(result.score, 0.0)
        self.assertAlmostEqual(result.confidence, 0.0)

    def test_document_agnostic_fallback_does_not_require_contract_language(self):
        # A genuine, well-formed but non-contract, non-registered document
        # (no "agreement/policy/contract" title word, no "between X and Y"
        # parties, no "in witness whereof" signature) should still score
        # well against the document-agnostic template purely on heading +
        # reference number + date -- the concrete case this fallback exists
        # to fix.
        text = "CITY MUNICIPAL AUTHORITY\nNotice Ref: NOT-2024-771\nDated: 5th May 2024\nBy order of the Authority."
        # Force the Unknown path directly to exercise the fallback template
        # itself, independent of whatever the classifier happens to make of
        # this particular sentence (that's covered by test_document_classifier.py).
        unknown_classification = DocumentTypeClassification(document_type=UNKNOWN_DOCUMENT_TYPE, confidence=0.0)
        result = assess_structure(text, unknown_classification)
        self.assertEqual(result.template_used, GENERIC_DOCUMENT_AGNOSTIC_KEY)
        self.assertEqual(result.missing_sections, [])
        self.assertAlmostEqual(result.score, 1.0)

    def test_registered_type_with_no_structure_template_falls_back_to_generic(self):
        # A document type the classifier knows about but that has no entry
        # in document_structure_rules.json yet -- must degrade gracefully,
        # not raise.
        fake_classification = DocumentTypeClassification(
            document_type="Sale Deed", confidence=0.9,  # not in document_structure_rules.json
        )
        result = assess_structure("This sale deed transfers the property.", fake_classification)
        self.assertEqual(result.template_used, GENERIC_MINIMAL_KEY)

    def test_empty_text(self):
        classification = classify_document_type_ranked("")
        result = assess_structure("", classification)
        self.assertAlmostEqual(result.score, 0.0)
        self.assertEqual(result.found_sections, [])


class SectionNumberingSignalTests(unittest.TestCase):
    def test_non_decreasing_numbering_scores_full(self):
        classification = classify_document_type_ranked(GOOD_INSURANCE_POLICY)
        clauses = [
            {"section_name": "1. Policy Number"}, {"section_name": "2. Sum Assured"}, {"section_name": "3. Premium"},
        ]
        result = assess_structure(GOOD_INSURANCE_POLICY, classification, clauses=clauses)
        self.assertEqual(result.section_numbering_score, 1.0)
        self.assertTrue(any("consistent, non-decreasing" in e for e in result.evidence))

    def test_out_of_order_numbering_scores_zero_and_lowers_overall_score(self):
        classification = classify_document_type_ranked(GOOD_INSURANCE_POLICY)
        ordered_clauses = [{"section_name": "1. A"}, {"section_name": "2. B"}, {"section_name": "3. C"}]
        broken_clauses = [{"section_name": "1. A"}, {"section_name": "5. B"}, {"section_name": "2. C"}]
        ordered_result = assess_structure(GOOD_INSURANCE_POLICY, classification, clauses=ordered_clauses)
        broken_result = assess_structure(GOOD_INSURANCE_POLICY, classification, clauses=broken_clauses)
        self.assertEqual(broken_result.section_numbering_score, 0.0)
        self.assertLess(broken_result.score, ordered_result.score)

    def test_fewer_than_two_numbered_sections_is_not_checkable(self):
        classification = classify_document_type_ranked(GOOD_INSURANCE_POLICY)
        result = assess_structure(GOOD_INSURANCE_POLICY, classification, clauses=[{"section_name": "Preamble"}])
        self.assertIsNone(result.section_numbering_score)
        self.assertTrue(any("Section numbering: not checkable" in e for e in result.evidence))


class PageContinuitySignalTests(unittest.TestCase):
    def test_contiguous_pages_score_full(self):
        classification = classify_document_type_ranked(GOOD_INSURANCE_POLICY)
        pages = [{"page_number": i, "raw_text": "x"} for i in (1, 2, 3)]
        result = assess_structure(GOOD_INSURANCE_POLICY, classification, pages=pages)
        self.assertEqual(result.page_continuity_score, 1.0)

    def test_gap_in_pages_lowers_continuity_and_overall_score(self):
        classification = classify_document_type_ranked(GOOD_INSURANCE_POLICY)
        contiguous_pages = [{"page_number": i, "raw_text": "x"} for i in (1, 2, 3)]
        gapped_pages = [{"page_number": i, "raw_text": "x"} for i in (1, 2, 4)]  # page 3 missing
        contiguous_result = assess_structure(GOOD_INSURANCE_POLICY, classification, pages=contiguous_pages)
        gapped_result = assess_structure(GOOD_INSURANCE_POLICY, classification, pages=gapped_pages)
        self.assertAlmostEqual(gapped_result.page_continuity_score, 0.75, places=4)
        self.assertLess(gapped_result.score, contiguous_result.score)

    def test_single_page_is_not_checkable(self):
        classification = classify_document_type_ranked(GOOD_INSURANCE_POLICY)
        result = assess_structure(GOOD_INSURANCE_POLICY, classification, pages=[{"page_number": 1, "raw_text": "x"}])
        self.assertIsNone(result.page_continuity_score)


if __name__ == "__main__":
    unittest.main()
