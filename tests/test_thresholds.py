"""Unit tests for risk_engine/thresholds.py — the Jenks-natural-breaks
replacement for the fixed 35/70 and 35/60/80 classification cut points.

Run with:  python -m unittest discover -s tests
"""

import random
import unittest

from risk_engine import fusion
from risk_engine.hybrid_engine import HybridExplainableRiskEngine
from risk_engine.thresholds import (
    DEFAULT_CLAUSE_CUTS,
    DEFAULT_DOCUMENT_CUTS,
    MIN_REFERENCE_SIZE,
    ThresholdRegistry,
    compute_thresholds,
    jenks_breaks,
)


class JenksBreaksTests(unittest.TestCase):
    def test_separates_well_defined_clusters(self):
        # Interior breaks land on the max of each lower cluster (Jenks
        # returns actual data values, not gap midpoints) — see the
        # jenks_breaks docstring for why classify() still works correctly
        # with these as inclusive-lower-bound-of-next-class cuts.
        data = [1, 1, 1, 2, 2, 1.5] + [39, 40, 40.5, 41, 42] + [94, 95, 95.5, 96, 97]
        breaks = jenks_breaks(data, 3)
        self.assertEqual(breaks[0], 1)
        self.assertEqual(breaks[1], 2)
        self.assertEqual(breaks[2], 42)
        self.assertEqual(breaks[3], 97)

    def test_requires_at_least_n_classes_values(self):
        with self.assertRaises(ValueError):
            jenks_breaks([1.0, 2.0], n_classes=3)

    def test_four_class_breaks_are_monotonic(self):
        rng = random.Random(0)
        data = [rng.gauss(50, 20) for _ in range(300)]
        breaks = jenks_breaks(data, 4)
        self.assertEqual(len(breaks), 5)
        self.assertEqual(breaks, sorted(breaks))


class ComputeThresholdsTests(unittest.TestCase):
    def test_falls_back_below_min_reference_size(self):
        result = compute_thresholds([10.0] * (MIN_REFERENCE_SIZE - 1), n_classes=3,
                                     fallback_cuts=DEFAULT_CLAUSE_CUTS)
        self.assertFalse(result.is_data_derived)
        self.assertEqual(result.cuts, DEFAULT_CLAUSE_CUTS)

    def test_uses_jenks_at_or_above_min_reference_size(self):
        rng = random.Random(1)
        low = [rng.gauss(15, 5) for _ in range(20)]
        mid = [rng.gauss(50, 5) for _ in range(20)]
        high = [rng.gauss(85, 5) for _ in range(20)]
        result = compute_thresholds(low + mid + high, n_classes=3, fallback_cuts=DEFAULT_CLAUSE_CUTS)
        self.assertTrue(result.is_data_derived)
        self.assertEqual(len(result.cuts), 2)
        # Cuts should sit roughly between the synthetic clusters, not at
        # the arbitrary fixed defaults.
        self.assertTrue(20 < result.cuts[0] < 70)
        self.assertTrue(result.cuts[0] < result.cuts[1])

    def test_ignores_none_values(self):
        result = compute_thresholds([None] * 50 + [10.0] * 5, n_classes=3, fallback_cuts=DEFAULT_CLAUSE_CUTS)
        self.assertFalse(result.is_data_derived)  # only 5 real values, below MIN_REFERENCE_SIZE
        self.assertEqual(result.sample_size, 5)


class ThresholdRegistryTests(unittest.TestCase):
    def test_caches_until_refresh(self):
        calls = {"n": 0}

        def fetch():
            calls["n"] += 1
            return [10.0] * 40  # stable small-spread reference set

        registry = ThresholdRegistry(fetch_clause_scores=fetch, fetch_document_scores=lambda: [])
        registry.clause_thresholds()
        registry.clause_thresholds()
        registry.clause_thresholds()
        self.assertEqual(calls["n"], 1)  # only fetched once, cached thereafter

        registry.refresh_clause_thresholds()
        self.assertEqual(calls["n"], 2)

    def test_document_thresholds_independent_of_clause_thresholds(self):
        registry = ThresholdRegistry(
            fetch_clause_scores=lambda: [],
            fetch_document_scores=lambda: [],
        )
        clause_result = registry.clause_thresholds()
        doc_result = registry.document_thresholds()
        self.assertEqual(clause_result.cuts, DEFAULT_CLAUSE_CUTS)
        self.assertEqual(doc_result.cuts, DEFAULT_DOCUMENT_CUTS)


class EngineUsesInjectedThresholdsTests(unittest.TestCase):
    def _fake_embed(self, texts):
        import numpy as np
        return np.ones((len(texts), 4)) * 0.5  # content doesn't matter for this test

    def test_score_document_calls_threshold_fn_and_uses_its_cuts(self):
        calls = {"n": 0}

        def get_thresholds():
            calls["n"] += 1
            return (1.0, 2.0)  # absurdly low cuts -> every clause should read "High"

        from risk_engine.schemas import ClauseInput, LegalFeatureVector

        engine = HybridExplainableRiskEngine(embed_fn=self._fake_embed, get_clause_thresholds=get_thresholds)
        clauses = [
            ClauseInput(clause_id=1, text="A clause.", features=LegalFeatureVector(clause_id=1)),
            ClauseInput(clause_id=2, text="Another clause.", features=LegalFeatureVector(clause_id=2)),
        ]
        result = engine.score_document(clauses)

        self.assertGreaterEqual(calls["n"], 1)
        for assessment in result.clause_assessments:
            self.assertEqual(assessment.classification, "High")


if __name__ == "__main__":
    unittest.main()
