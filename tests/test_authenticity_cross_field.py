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

    def test_inflated_sum_assured_is_detected_2026_07_26_audit_regression(self):
        # The exact false positive confirmed during the 2026-07-26 audit: an
        # 80%-inflated Sum Assured (Rs. 5,00,000 -> Rs. 9,00,000) used to be
        # reported as "CONSISTENT (minor formatting variation only)" under
        # the old character-similarity fuzzy match (0.833 ratio, above the
        # 0.5 threshold). Sum Assured is a declared 'money' field in
        # rules/cross_field_rules.json, so this now goes through
        # field_matching.numeric_match_fraction instead.
        tampered_sum_assured = """
INSURANCE POLICY

Policy Number: POL-88213-A
Sum Assured: Rs. 5,00,000

Endorsement: This endorsement is issued under Policy No: POL-88213-A.
The Sum Assured payable under this policy remains Rs. 9,00,000.
"""
        classification = DocumentTypeClassification(document_type="Insurance Policy", confidence=1.0)
        result = assess_cross_field_consistency(tampered_sum_assured, classification)
        sum_assured_check = next(f for f in result.checked_fields if f.field_name == "Sum Assured")
        self.assertFalse(sum_assured_check.consistent)
        self.assertLess(sum_assured_check.match_fraction, 1.0)
        self.assertTrue(any("INCONSISTENT" in e and "Sum Assured" in e for e in result.evidence))
        self.assertLess(result.score, 1.0)


class ExtractionCorrectnessTests(unittest.TestCase):
    def test_repeated_page_header_after_a_label_is_not_captured_as_a_value(self):
        # 2026-07-26 extraction-correctness follow-up: root cause of the
        # real 78->74 score drop on 471051998_1.pdf. The Policy Number
        # regex is compiled with re.IGNORECASE for its "policy no/number"
        # LABEL text, but its VALUE capture group ([A-Z0-9][A-Z0-9-/]*) was
        # ALSO affected by that flag -- under IGNORECASE, [A-Z0-9] matches
        # lowercase letters too, so a plain word immediately following the
        # label satisfied the "value" pattern. The real document has a
        # repeated page-header artifact right after a genuine label:
        # "Previous Policy No. Policy Schedule Table 2 (Page 6)" -- the
        # word "Policy" (from the header) was captured as if it were a
        # policy number. Fixed with a scoped (?-i:...) flag that keeps the
        # label case-insensitive while requiring the captured value to be
        # genuinely uppercase/digit.
        text_with_header_artifact = (
            "Policy Number: OG-24-3307-1802-00000030\n"
            "Previous Policy No. Policy Schedule Table 2 (Page 6)\n"
            "Endorsement issued under Policy No: OG-24-3307-1802-00000030\n"
        )
        classification = DocumentTypeClassification(document_type="Insurance Policy", confidence=1.0)
        result = assess_cross_field_consistency(text_with_header_artifact, classification)
        policy_number_check = next(f for f in result.checked_fields if f.field_name == "Policy Number")
        # Only the 2 GENUINE mentions were extracted; the page-header
        # artifact ("Policy Schedule...") contributed nothing, so this
        # correctly reads as consistent rather than being diluted by a
        # bogus third "value".
        self.assertNotIn("POLICY", [v.upper() for v in policy_number_check.occurrences])
        self.assertEqual(policy_number_check.occurrences, ["OG-24-3307-1802-00000030", "OG-24-3307-1802-00000030"])
        self.assertTrue(policy_number_check.consistent)

    def test_previous_policy_number_is_not_conflated_with_the_current_one(self):
        # A real insurance renewal document legitimately restates its OWN
        # prior policy number for reference alongside its current one --
        # two genuinely different fields, not a tampering signal. Also
        # covers the actual real-document quirk found while investigating
        # the score drop: this PDF's page-level text extraction drops
        # inter-word spaces in places ("PreviousPolicyNo:OG-23-...").
        text = (
            "PreviousPolicyNo:OG-23-3307-1802-00000042\n"
            "Policy Number: OG-24-3307-1802-00000030\n"
            "Endorsement issued under Policy No: OG-24-3307-1802-00000030\n"
        )
        classification = DocumentTypeClassification(document_type="Insurance Policy", confidence=1.0)
        result = assess_cross_field_consistency(text, classification)
        policy_number_check = next(f for f in result.checked_fields if f.field_name == "Policy Number")
        self.assertNotIn("OG-23-3307-1802-00000042", policy_number_check.occurrences)
        self.assertEqual(policy_number_check.occurrences, ["OG-24-3307-1802-00000030", "OG-24-3307-1802-00000030"])
        self.assertTrue(policy_number_check.consistent)

    def test_genuine_value_extraction_still_works_after_the_fix(self):
        # The fix must not break real, legitimate repeated-value extraction.
        text = "Policy Number: POL-88213-A ... Policy No: POL-88213-A"
        classification = DocumentTypeClassification(document_type="Insurance Policy", confidence=1.0)
        result = assess_cross_field_consistency(text, classification)
        policy_number_check = next(f for f in result.checked_fields if f.field_name == "Policy Number")
        self.assertEqual(policy_number_check.occurrences, ["POL-88213-A", "POL-88213-A"])
        self.assertTrue(policy_number_check.consistent)


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
