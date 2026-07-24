"""Tests for authenticity/dai.py — the Document Authenticity Index fusion
stage combining all factors (7 generic + the additive document-type-validator
factor). Uses lightweight stub factor results (not
the real factor modules, which need spaCy/embeddings/pikepdf fixtures) so
this suite stays fast and focused purely on the fusion math.

Run with:  python -m unittest discover -s tests
"""

import unittest

import numpy as np

from authenticity.dai import FACTOR_NAMES, assess_document_authenticity


class _Stub:
    def __init__(self, applicable=True, score=0.0, confidence=0.0):
        self.applicable = applicable
        self.score = score
        self.confidence = confidence


def _all_factors(score: float, confidence: float = 80.0):
    return {name: _Stub(True, score, confidence) for name in FACTOR_NAMES}


class EqualWeightFallbackTests(unittest.TestCase):
    def test_all_applicable_equal_scores_gives_that_score_times_100(self):
        result = assess_document_authenticity(_all_factors(0.8))
        self.assertAlmostEqual(result.dai_score, 80.0, places=2)
        self.assertFalse(result.weights_data_derived)

    def test_weights_sum_to_one_and_are_equal_at_cold_start(self):
        result = assess_document_authenticity(_all_factors(0.5))
        weights = [c.weight for c in result.contributions]
        # places=2, not 4: each weight is individually rounded to 4dp before
        # this sum, so summing 7 of them can drift by a few 1e-4 -- the same
        # rounding-before-summing artifact documented for the risk engine's
        # dimension_weights, not a fusion-math bug.
        self.assertAlmostEqual(sum(weights), 1.0, places=2)
        self.assertTrue(all(abs(w - weights[0]) < 1e-9 for w in weights))


class NotApplicableExclusionTests(unittest.TestCase):
    def test_not_applicable_factor_is_excluded_and_weight_redistributed(self):
        factors = _all_factors(0.9)
        factors["digital_verification"] = _Stub(applicable=False, score=0.0, confidence=0.0)
        result = assess_document_authenticity(factors)
        names_used = [c.name for c in result.contributions]
        self.assertNotIn("digital_verification", names_used)
        self.assertEqual(len(result.contributions), 7)
        self.assertAlmostEqual(result.dai_score, 90.0, places=2)
        self.assertIn("digital_verification", " ".join(result.evidence))

    def test_missing_factor_key_treated_like_not_applicable(self):
        factors = _all_factors(0.9)
        del factors["metadata_validation"]
        result = assess_document_authenticity(factors)
        self.assertEqual(len(result.contributions), 7)

    def test_all_factors_not_applicable_is_insufficient_signal(self):
        factors = {name: _Stub(applicable=False) for name in FACTOR_NAMES}
        result = assess_document_authenticity(factors)
        self.assertEqual(result.authenticity_level, "Insufficient Signal")
        self.assertEqual(result.dai_score, 0.0)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.contributions, [])


class ClassificationTierTests(unittest.TestCase):
    def test_high_score_is_authentic(self):
        result = assess_document_authenticity(_all_factors(0.9))
        self.assertEqual(result.authenticity_level, "Authentic")

    def test_mid_high_score_is_likely_authentic(self):
        result = assess_document_authenticity(_all_factors(0.7))
        self.assertEqual(result.authenticity_level, "Likely Authentic")

    def test_mid_score_is_suspicious(self):
        result = assess_document_authenticity(_all_factors(0.5))
        self.assertEqual(result.authenticity_level, "Suspicious")

    def test_low_score_is_highly_suspicious(self):
        result = assess_document_authenticity(_all_factors(0.2))
        self.assertEqual(result.authenticity_level, "Highly Suspicious")


class ReferenceCorpusEntropyWeightTests(unittest.TestCase):
    def test_sufficient_reference_history_uses_data_derived_weights(self):
        # A factor with zero variance across history (always 0.9) should be
        # down-weighted relative to one that varies a lot (0.1 .. 0.9).
        rng = np.random.default_rng(42)
        reference_corpus = []
        for _ in range(40):
            reference_corpus.append({
                "structure": 0.9,  # constant -- low discriminative power
                "clause_completeness": float(rng.uniform(0.1, 0.9)),  # varies -- high discriminative power
                "cross_field": 0.9,
                "entity_verification": 0.9,
                "digital_verification": 0.9,
                "metadata_validation": 0.9,
                "semantic_consistency": 0.9,
                "document_type_validator": 0.9,
            })

        result = assess_document_authenticity(_all_factors(0.9), reference_corpus=reference_corpus)
        self.assertTrue(result.weights_data_derived)
        weight_by_name = {c.name: c.weight for c in result.contributions}
        self.assertGreater(weight_by_name["clause_completeness"], weight_by_name["structure"])

    def test_incomplete_reference_rows_are_excluded(self):
        # Rows missing one of the currently-applicable factors must not be
        # used -- comparing entropy across mismatched factor sets would be
        # meaningless. With only 1 complete row (< 2), falls back to equal
        # weights just like having no reference corpus at all.
        reference_corpus = [{"structure": 0.5}] * 40  # missing every other factor
        result = assess_document_authenticity(_all_factors(0.6), reference_corpus=reference_corpus)
        self.assertFalse(result.weights_data_derived)


if __name__ == "__main__":
    unittest.main()
