"""Tests for authenticity/cross_field.py (Factor 3 of the Authenticity
Verification Engine) — same-field, cross-location value consistency,
graceful non-applicability for unregistered document types, and the
"nothing repeated, nothing to check" zero-evidence case.

Run with:  python -m unittest discover -s tests
"""

import unittest

from authenticity.cross_field import assess_cross_field_consistency
from services.document_classifier import DocumentTypeClassification

CONSISTENT_POLICY = """
INSURANCE POLICY

Policy Number: POL-88213-A
Sum Assured: Rs. 5,00,000

...coverage terms follow...

Endorsement: This endorsement is issued under Policy No: POL-88213-A.
The Sum Assured payable under this policy remains Rs. 5,00,000.
"""

TAMPERED_POLICY = """
INSURANCE POLICY

Policy Number: POL-88213-A
Sum Assured: Rs. 5,00,000

...coverage terms follow...

Endorsement: This endorsement is issued under Policy No: POL-99999-Z.
The Sum Assured payable under this policy remains Rs. 5,00,000.
"""

SINGLE_MENTION_POLICY = """
INSURANCE POLICY

Policy Number: POL-88213-A
Sum Assured: Rs. 5,00,000
"""

# One-character OCR misread (8 -> B) in the second mention -- the kind of
# noise a real scanned multi-page policy produces. Regression fixture for
# the false-positive this factor originally raised on a real document: the
# same policy number, scanned twice, read as two different strings.
OCR_NOISY_POLICY = """
INSURANCE POLICY

Policy Number: POL-88213-A
Sum Assured: Rs. 5,00,000

...coverage terms follow...

Endorsement: This endorsement is issued under Policy No: POL-8B213-A.
The Sum Assured payable under this policy remains Rs. 5,00,000.
"""


class ConsistentFieldsTests(unittest.TestCase):
    def test_matching_repeated_values_score_perfect(self):
        classification = DocumentTypeClassification(document_type="Insurance Policy", confidence=1.0)
        result = assess_cross_field_consistency(CONSISTENT_POLICY, classification)
        self.assertTrue(result.applicable)
        self.assertEqual(result.score, 1.0)
        self.assertTrue(all(f.consistent for f in result.checked_fields))


class OcrNoiseToleranceTests(unittest.TestCase):
    def test_single_character_ocr_noise_still_fuzzy_matches(self):
        # Regression test: exact-match normalization treated this as a
        # tampered policy number before the fuzzy-match fix -- it's really
        # the same value with one OCR-misread character.
        classification = DocumentTypeClassification(document_type="Insurance Policy", confidence=1.0)
        result = assess_cross_field_consistency(OCR_NOISY_POLICY, classification)
        policy_number_check = next(f for f in result.checked_fields if f.field_name == "Policy Number")
        self.assertTrue(policy_number_check.consistent)
        self.assertEqual(policy_number_check.match_fraction, 1.0)
        self.assertEqual(result.score, 1.0)
        self.assertTrue(any("minor formatting variation" in e for e in result.evidence))


class InconsistentFieldsTests(unittest.TestCase):
    def test_mismatched_policy_number_is_flagged_and_lowers_score(self):
        classification = DocumentTypeClassification(document_type="Insurance Policy", confidence=1.0)
        result = assess_cross_field_consistency(TAMPERED_POLICY, classification)
        self.assertTrue(result.applicable)
        self.assertLess(result.score, 1.0)
        policy_number_check = next(f for f in result.checked_fields if f.field_name == "Policy Number")
        self.assertFalse(policy_number_check.consistent)
        sum_assured_check = next(f for f in result.checked_fields if f.field_name == "Sum Assured")
        self.assertTrue(sum_assured_check.consistent)
        self.assertTrue(any("INCONSISTENT" in e and "Policy Number" in e for e in result.evidence))


class NoRepetitionTests(unittest.TestCase):
    def test_fields_mentioned_only_once_are_not_checkable(self):
        classification = DocumentTypeClassification(document_type="Insurance Policy", confidence=1.0)
        result = assess_cross_field_consistency(SINGLE_MENTION_POLICY, classification)
        self.assertTrue(result.applicable)
        self.assertEqual(result.score, 1.0)  # vacuously consistent -- nothing contradicted
        self.assertEqual(result.confidence, 0.0)  # but zero evidence was actually gathered
        self.assertEqual(result.checked_fields, [])


class NotApplicableTests(unittest.TestCase):
    def test_unregistered_document_type_is_not_applicable(self):
        classification = DocumentTypeClassification(document_type="Non-Disclosure Agreement (NDA)", confidence=1.0)
        result = assess_cross_field_consistency("some nda text", classification)
        self.assertFalse(result.applicable)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)

    def test_unknown_document_type_is_not_applicable(self):
        classification = DocumentTypeClassification(document_type="Unknown Document", confidence=0.0)
        result = assess_cross_field_consistency("", classification)
        self.assertFalse(result.applicable)


class ConfidenceDiscountTests(unittest.TestCase):
    def test_low_type_confidence_discounts_confidence_not_score(self):
        high_c = DocumentTypeClassification(document_type="Insurance Policy", confidence=1.0)
        low_c = DocumentTypeClassification(document_type="Insurance Policy", confidence=0.0)
        result_high = assess_cross_field_consistency(CONSISTENT_POLICY, high_c)
        result_low = assess_cross_field_consistency(CONSISTENT_POLICY, low_c)
        self.assertEqual(result_high.score, result_low.score)
        self.assertLess(result_low.confidence, result_high.confidence)
        self.assertGreater(result_low.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
