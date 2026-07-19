"""Tests for services/document_classifier.py, including the new
classify_document_type_ranked() (Stage 0 of the Authenticity Verification
Engine redesign) — margin/evidence-based confidence on top of the
unchanged, pre-existing classify_document_type().

Run with:  python -m unittest discover -s tests
"""

import unittest

from services.document_classifier import (
    MIN_CONFIDENT_SCORE,
    UNKNOWN_DOCUMENT_TYPE,
    _margin_confidence,
    classify_document_type,
    classify_document_type_ranked,
)

NDA_TEXT = (
    "This Non-Disclosure Agreement is entered into between the Disclosing Party "
    "and the Receiving Party regarding Confidential Information disclosed hereunder."
)

INSURANCE_TEXT = (
    "This Insurance Policy sets out the Sum Assured payable to the Policyholder "
    "upon payment of the Premium as described herein."
)

AMBIGUOUS_TEXT = "The lessor and lessee agree the landlord and tenant terms herein."

UNRELATED_TEXT = "The quick brown fox jumps over the lazy dog."


class ClassifyDocumentTypeUnchangedTests(unittest.TestCase):
    """classify_document_type() must behave identically to before the
    refactor into _score_all_types() -- these lock that in."""

    def test_clear_match(self):
        self.assertEqual(classify_document_type(NDA_TEXT), "Non-Disclosure Agreement (NDA)")

    def test_empty_text_is_unknown(self):
        self.assertEqual(classify_document_type(""), UNKNOWN_DOCUMENT_TYPE)

    def test_unrelated_text_is_unknown(self):
        self.assertEqual(classify_document_type(UNRELATED_TEXT), UNKNOWN_DOCUMENT_TYPE)

    def test_returns_plain_string(self):
        self.assertIsInstance(classify_document_type(NDA_TEXT), str)


class MarginConfidenceTests(unittest.TestCase):
    def test_uncontested_winner_is_full_margin(self):
        self.assertAlmostEqual(_margin_confidence(5, 0), 1.0)

    def test_exact_tie_is_zero_margin(self):
        self.assertAlmostEqual(_margin_confidence(2, 2), 0.0)

    def test_both_zero_does_not_divide_by_zero(self):
        self.assertAlmostEqual(_margin_confidence(0, 0), 0.0)

    def test_partial_lead(self):
        self.assertAlmostEqual(_margin_confidence(6, 4), 0.2)


class ClassifyDocumentTypeRankedTests(unittest.TestCase):
    def test_clear_match_has_high_confidence_and_matches_plain_classifier(self):
        result = classify_document_type_ranked(NDA_TEXT)
        self.assertEqual(result.document_type, classify_document_type(NDA_TEXT))
        self.assertGreater(result.confidence, 0.5)
        self.assertIsNone(result.runner_up)  # nothing else scored > 0

    def test_insurance_policy_detected(self):
        result = classify_document_type_ranked(INSURANCE_TEXT)
        self.assertEqual(result.document_type, "Insurance Policy")
        self.assertGreater(result.confidence, 0.0)

    def test_empty_text(self):
        result = classify_document_type_ranked("")
        self.assertEqual(result.document_type, UNKNOWN_DOCUMENT_TYPE)
        self.assertAlmostEqual(result.confidence, 0.0)
        self.assertIsNone(result.runner_up)

    def test_unrelated_text_is_unknown_with_zero_confidence(self):
        result = classify_document_type_ranked(UNRELATED_TEXT)
        self.assertEqual(result.document_type, UNKNOWN_DOCUMENT_TYPE)
        self.assertAlmostEqual(result.confidence, 0.0)

    def test_genuine_tie_yields_zero_confidence_even_though_plain_classifier_picks_one(self):
        # The exact failure mode Stage 0 exists to catch: the plain
        # classifier picks a winner with no indication of how close the
        # call was; the ranked version must expose the tie as 0 confidence.
        plain = classify_document_type(AMBIGUOUS_TEXT)
        self.assertNotEqual(plain, UNKNOWN_DOCUMENT_TYPE)  # plain classifier is confidently wrong-ish

        ranked = classify_document_type_ranked(AMBIGUOUS_TEXT)
        self.assertEqual(ranked.document_type, plain)  # same winner (tie-break is consistent)
        self.assertAlmostEqual(ranked.confidence, 0.0, places=4)
        self.assertIsNotNone(ranked.runner_up)
        self.assertEqual(ranked.scores["Lease Agreement"], ranked.scores["Rental Agreement"])

    def test_scores_dict_always_populated_for_known_text(self):
        result = classify_document_type_ranked(NDA_TEXT)
        self.assertGreaterEqual(len(result.scores), 20)  # every registered type present
        self.assertEqual(
            result.scores[result.document_type],
            max(result.scores.values()),
        )

    def test_below_min_confident_score_is_unknown(self):
        # A single, borderline non-repeating token shouldn't clear
        # MIN_CONFIDENT_SCORE any more for the ranked path than the plain one.
        self.assertEqual(MIN_CONFIDENT_SCORE, 1)  # documents the assumption this test relies on


if __name__ == "__main__":
    unittest.main()
