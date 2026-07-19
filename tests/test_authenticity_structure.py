"""Tests for authenticity/structure.py (Factor 1 of the Authenticity
Verification Engine) — continuous fraction-based structure scoring,
confidence-weighted blending between the type-specific and generic-minimal
templates, and graceful fallback for unrecognized document types.

Run with:  python -m unittest discover -s tests
"""

import unittest

from authenticity.structure import GENERIC_MINIMAL_KEY, assess_structure
from services.document_classifier import DocumentTypeClassification, classify_document_type_ranked

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


class LowConfidenceBlendingTests(unittest.TestCase):
    def test_zero_confidence_classification_uses_generic_template_only(self):
        classification = classify_document_type_ranked(AMBIGUOUS_TEXT)
        self.assertAlmostEqual(classification.confidence, 0.0, places=4)

        result = assess_structure(AMBIGUOUS_TEXT, classification)
        generic_only = assess_structure(AMBIGUOUS_TEXT, DocumentTypeClassification(
            document_type=GENERIC_MINIMAL_KEY, confidence=0.0,
        ))
        # At c=0 the blend collapses entirely onto the generic template's
        # own fractional score for the same text.
        generic_direct_score = None
        from authenticity.structure import _check_template, _fraction, _normalize
        f, m = _check_template(_normalize(AMBIGUOUS_TEXT), GENERIC_MINIMAL_KEY)
        generic_direct_score = _fraction(f, m)
        self.assertAlmostEqual(result.score, generic_direct_score, places=4)
        self.assertIn("Blended 0% weight on the type-specific template", " ".join(result.evidence))

    def test_confidence_between_0_and_1_produces_a_true_blend(self):
        # A synthetic mid-confidence classification over real insurance
        # text should land strictly between the pure type-specific score
        # and the pure generic score, not equal either endpoint.
        from authenticity.structure import _check_template, _fraction, _normalize
        normalized = _normalize(GOOD_INSURANCE_POLICY)
        type_found, type_missing = _check_template(normalized, "Insurance Policy")
        type_score = _fraction(type_found, type_missing)
        generic_found, generic_missing = _check_template(normalized, GENERIC_MINIMAL_KEY)
        generic_score = _fraction(generic_found, generic_missing)
        self.assertNotAlmostEqual(type_score, generic_score, places=2)  # test is only meaningful if these differ

        mid_confidence = DocumentTypeClassification(document_type="Insurance Policy", confidence=0.5)
        result = assess_structure(GOOD_INSURANCE_POLICY, mid_confidence)
        expected = 0.5 * type_score + 0.5 * generic_score
        self.assertAlmostEqual(result.score, expected, places=4)


class NoTemplateFallbackTests(unittest.TestCase):
    def test_unknown_document_type_falls_back_to_generic(self):
        classification = classify_document_type_ranked(UNRELATED_TEXT)
        result = assess_structure(UNRELATED_TEXT, classification)
        self.assertEqual(result.template_used, GENERIC_MINIMAL_KEY)
        self.assertAlmostEqual(result.score, 0.0)
        self.assertAlmostEqual(result.confidence, 0.0)

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


if __name__ == "__main__":
    unittest.main()
