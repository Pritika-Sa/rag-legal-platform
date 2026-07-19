"""Unit tests for risk_engine/, run against synthetic LegalFeatureVectors
and a deterministic fake embedding function — deliberately not the real
sentence-transformer model, so these run fast and offline, ahead of
agents/feature_extraction_agent.py (which doesn't exist yet) actually
producing LegalFeatureVectors from real documents.

Run with:  python -m unittest discover -s tests
"""

import hashlib
import unittest

import numpy as np

from risk_engine import fusion
from risk_engine.dimensions import _financial_raw, _percentile_normalize, feature_evidence
from risk_engine.explain import compute_confidence_scores
from risk_engine.hybrid_engine import HybridExplainableRiskEngine
from risk_engine.schemas import (
    ClauseInput, Deadline, FinancialTerm, LegalAction, LegalFeatureVector, Obligation, Polarity,
)


class FuseSignalTests(unittest.TestCase):
    def test_alpha_one_is_feature_only(self):
        self.assertAlmostEqual(fusion.fuse_signal(0.8, 0.1, alpha=1.0), 0.8)

    def test_alpha_zero_is_semantic_only(self):
        self.assertAlmostEqual(fusion.fuse_signal(0.8, 0.1, alpha=0.0), 0.1)

    def test_alpha_half_is_average(self):
        self.assertAlmostEqual(fusion.fuse_signal(0.8, 0.2, alpha=0.5), 0.5)

    def test_clamped_to_unit_interval(self):
        self.assertLessEqual(fusion.fuse_signal(1.0, 1.0, alpha=0.5), 1.0)
        self.assertGreaterEqual(fusion.fuse_signal(0.0, 0.0, alpha=0.5), 0.0)


class DynamicAlphaTests(unittest.TestCase):
    def test_favors_the_more_discriminative_branch(self):
        # F_d varies a lot across these clauses (informative for this
        # document); E_d is nearly constant (uninformative) -> alpha
        # should favor the feature branch, i.e. be > 0.5.
        rng = np.random.default_rng(3)
        feature_signals = rng.random(200)
        semantic_signals = np.full(200, 0.5) + rng.normal(0, 0.001, 200)
        alpha = fusion.dynamic_alpha(feature_signals, semantic_signals)
        self.assertGreater(alpha, 0.5)

    def test_favors_the_semantic_branch_when_reversed(self):
        rng = np.random.default_rng(4)
        feature_signals = np.full(200, 0.5) + rng.normal(0, 0.001, 200)
        semantic_signals = rng.random(200)
        alpha = fusion.dynamic_alpha(feature_signals, semantic_signals)
        self.assertLess(alpha, 0.5)

    def test_small_n_shrinks_toward_equal_trust(self):
        alpha = fusion.dynamic_alpha(np.array([0.9, 0.1]), np.array([0.1, 0.9]))
        self.assertAlmostEqual(alpha, 0.5, places=1)

    def test_bounded_in_unit_interval(self):
        rng = np.random.default_rng(5)
        alpha = fusion.dynamic_alpha(rng.random(500), rng.random(500))
        self.assertGreaterEqual(alpha, 0.0)
        self.assertLessEqual(alpha, 1.0)

    def test_negative_semantic_values_do_not_crash(self):
        # cosine similarity can in principle dip slightly negative
        alpha = fusion.dynamic_alpha(np.array([0.8, 0.2, 0.5] * 20), np.array([-0.1, 0.9, 0.3] * 20))
        self.assertGreaterEqual(alpha, 0.0)
        self.assertLessEqual(alpha, 1.0)


class ConfidenceScoresTests(unittest.TestCase):
    def test_weights_sum_to_one_and_bounded(self):
        f_signals = [{"Financial": v, "Legal": v} for v in np.linspace(0.1, 0.9, 30)]
        s_signals = [{"Financial": v, "Legal": 1 - v} for v in np.linspace(0.1, 0.9, 30)]
        feature_conf = [[0.5, 0.6] for _ in range(30)]

        scores, weights = compute_confidence_scores(f_signals, s_signals, feature_conf)

        self.assertEqual(len(scores), 30)
        self.assertTrue(all(0.0 <= s <= 100.0 for s in scores))
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=2)
        self.assertEqual(set(weights.keys()), {"agreement", "feature_confidence", "margin"})

    def test_single_clause_falls_back_to_equal_component_weights(self):
        f_signals = [{"Financial": 0.7, "Legal": 0.3}]
        s_signals = [{"Financial": 0.6, "Legal": 0.4}]
        feature_conf = [[0.8]]

        _scores, weights = compute_confidence_scores(f_signals, s_signals, feature_conf)
        for v in weights.values():
            self.assertAlmostEqual(v, 1 / 3, places=4)

    def test_more_variable_component_gets_more_weight(self):
        # "agreement" is engineered to swing wildly (F and E alternate
        # between matching and maximally opposed); "feature_confidence" is
        # engineered to barely move -> agreement should end up weighted
        # higher than feature_confidence.
        n = 40
        f_signals = [{"Financial": 0.9 if i % 2 == 0 else 0.1} for i in range(n)]
        s_signals = [{"Financial": 0.9 if i % 2 == 0 else 0.9} for i in range(n)]  # E constant -> swings agreement
        feature_conf = [[0.5000 + (0.0001 if i % 2 == 0 else 0.0)] for i in range(n)]  # nearly constant

        _scores, weights = compute_confidence_scores(f_signals, s_signals, feature_conf)
        self.assertGreater(weights["agreement"], weights["feature_confidence"])


class EntropyWeightsTests(unittest.TestCase):
    def test_single_clause_falls_back_to_equal_weights(self):
        w = fusion.entropy_weights(np.array([[0.9, 0.1, 0.5, 0.3, 0.7]]))
        self.assertTrue(np.allclose(w, 0.2))

    def test_weights_sum_to_one(self):
        matrix = np.random.default_rng(0).random((10, 5))
        w = fusion.entropy_weights(matrix)
        self.assertAlmostEqual(float(w.sum()), 1.0, places=6)

    def test_zero_variance_dimension_gets_near_minimal_but_nonzero_weight(self):
        # 4 dimensions vary a lot; the 5th is identical for every clause and
        # therefore carries no discriminative information. Use a large n so
        # the small-n shrinkage below doesn't wash out the effect.
        rng = np.random.default_rng(1)
        varying = rng.random((200, 4))
        constant = np.full((200, 1), 0.5)
        matrix = np.hstack([varying, constant])
        w = fusion.entropy_weights(matrix)
        self.assertGreater(w[:4].min(), w[4])  # constant column weighted below every varying one
        self.assertGreater(w[4], 0.0)          # but not literally zero (epsilon floor)

    def test_small_n_shrinks_toward_equal_weights(self):
        # Regression test for a real finding: with only 3 clauses, one
        # clause dominating a single dimension's column-sum (an "outlier")
        # made the raw Entropy Weight Method assign that dimension ~49% of
        # total influence, enough to rank a vague boilerplate clause above
        # one stating unlimited, uncapped liability. Shrinkage toward
        # uniform weights at small n bounds how much any one clause's
        # idiosyncrasy can swing a dimension's weight share.
        matrix = np.array([
            [0.42, 0.11],
            [0.73, 0.12],
            [0.14, 0.69],
        ])
        w = fusion.entropy_weights(matrix)
        self.assertLess(w.max() - w.min(), 0.3)  # far more balanced than the un-shrunk ~0.11 vs ~0.49 split

    def test_shrinkage_fades_out_at_large_n(self):
        # At large n the blend should sit close to the raw (unshrunk) EWM
        # weights, not the uniform prior — shrinkage exists for small
        # samples, not to permanently flatten every document's weights.
        rng = np.random.default_rng(2)
        matrix = rng.random((500, 5))
        raw = fusion._raw_entropy_weights(matrix, epsilon=1e-4)
        shrunk = fusion.entropy_weights(matrix)
        self.assertTrue(np.allclose(raw, shrunk, atol=0.05))


class LrsiAndClassifyTests(unittest.TestCase):
    def test_lrsi_scales_to_0_100(self):
        matrix = np.array([[1.0, 1.0, 1.0, 1.0, 1.0], [0.0, 0.0, 0.0, 0.0, 0.0]])
        weights = np.array([0.2, 0.2, 0.2, 0.2, 0.2])
        scores = fusion.lrsi_scores(matrix, weights)
        self.assertAlmostEqual(scores[0], 100.0)
        self.assertAlmostEqual(scores[1], 0.0)

    def test_classify_thresholds(self):
        self.assertEqual(fusion.classify(34.9), "Low")
        self.assertEqual(fusion.classify(35.0), "Medium")
        self.assertEqual(fusion.classify(69.9), "Medium")
        self.assertEqual(fusion.classify(70.0), "High")


class GiniAndDocumentRiskTests(unittest.TestCase):
    def test_gini_zero_when_all_equal(self):
        self.assertAlmostEqual(fusion.gini_coefficient(np.array([50.0, 50.0, 50.0])), 0.0)

    def test_gini_positive_when_skewed(self):
        g = fusion.gini_coefficient(np.array([10.0, 10.0, 10.0, 90.0]))
        self.assertGreater(g, 0.0)

    def test_document_risk_at_least_mean(self):
        values = np.array([10.0, 10.0, 90.0])
        doc_score = fusion.document_risk_score(values)
        self.assertGreaterEqual(doc_score, float(np.mean(values)))


class FinancialRawTests(unittest.TestCase):
    def test_uncapped_no_longer_multiplies_the_raw_score(self):
        # Regression test for dropping the old, hand-picked 1.3x "uncapped"
        # multiplier: the same dollar amount must produce the exact same
        # raw signal whether or not it's flagged as capped -- that
        # qualitative distinction is the semantic branch's job now (see
        # _financial_raw's docstring), not a second, arbitrary boost on
        # the feature branch.
        capped = LegalFeatureVector(
            clause_id=1, financial_terms=[FinancialTerm(amount=1_000_000.0, is_capped=True)],
        )
        uncapped = LegalFeatureVector(
            clause_id=2, financial_terms=[FinancialTerm(amount=1_000_000.0, is_capped=False)],
        )
        self.assertAlmostEqual(_financial_raw(capped), _financial_raw(uncapped))

    def test_uncapped_still_visible_in_feature_evidence(self):
        # is_capped isn't discarded -- it's just no longer a score
        # multiplier -- so it must still show up in the explainability text.
        uncapped = LegalFeatureVector(
            clause_id=1, financial_terms=[FinancialTerm(amount=500_000.0, currency="$", is_capped=False)],
        )
        evidence = feature_evidence(uncapped, "Financial")
        self.assertTrue(any("uncapped" in e for e in evidence))


class PercentileNormalizeTests(unittest.TestCase):
    def test_single_value(self):
        self.assertEqual(_percentile_normalize([5.0]), [0.5])

    def test_constant_values(self):
        self.assertEqual(_percentile_normalize([3.0, 3.0, 3.0]), [0.5, 0.5, 0.5])

    def test_distinct_values_rank_0_to_1(self):
        result = _percentile_normalize([10.0, 30.0, 20.0])
        self.assertAlmostEqual(result[0], 0.0)   # smallest
        self.assertAlmostEqual(result[2], 0.5)   # middle
        self.assertAlmostEqual(result[1], 1.0)   # largest


def _fake_embed(texts):
    """Deterministic test double standing in for a real sentence encoder:
    4 dims count hits from small token groups drawn from prototypes.json's
    own wording, plus 2 low-magnitude hash-noise dims. This is a TEST-ONLY
    stub simulating an embedding space so PrototypeStore similarity is
    controllable in isolation — it is not a reintroduction of keyword
    scoring into the engine itself, which never sees these token lists.

    The noise dims matter: without them, any two texts with zero hits in
    all 4 topic groups (e.g. a vague boilerplate clause and a prototype
    sentence whose wording this toy stub doesn't cover) collapse onto the
    exact same all-zero direction and register as a coincidental perfect
    cosine match — an artifact of a hand-rolled low-dimensional stub, not
    something a real trained encoder would do. The hash noise keeps
    unrelated "empty" texts from becoming exactly collinear.
    """
    financial_words = ["unlimited", "uncapped", "damages", "penalty", "cap", "payment", "accelerat"]
    legal_words = ["indemnif", "terminat", "waive", "liab"]
    compliance_words = ["regulat", "jurisdiction", "law", "sanction", "complian", "govern"]
    operational_words = ["deadline", "days", "milestone", "deliver", "service level"]
    groups = [financial_words, legal_words, compliance_words, operational_words]

    vectors = []
    for t in texts:
        t_low = t.lower()
        base = [float(sum(t_low.count(w) for w in group)) for group in groups]
        digest = hashlib.sha256(t.encode("utf-8")).digest()
        noise = [0.01 * (b / 255.0) for b in digest[:2]]
        vectors.append(base + noise)
    return np.array(vectors)


class HybridEngineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = HybridExplainableRiskEngine(embed_fn=_fake_embed)

    def _clause(self, clause_id, text, **feature_kwargs):
        return ClauseInput(
            clause_id=clause_id, text=text,
            features=LegalFeatureVector(clause_id=clause_id, **feature_kwargs),
        )

    def test_high_financial_exposure_outranks_boilerplate(self):
        high_risk = self._clause(
            1,
            "The Vendor's liability shall be unlimited and uncapped for any damages "
            "arising from this agreement, with no cap of liability.",
            financial_terms=[FinancialTerm(amount=5_000_000, currency="$", is_capped=False)],
            obligations=[Obligation(subject="Vendor", modal="shall", polarity=Polarity.OBLIGATION,
                                     action="be liable without limit", confidence=0.9)],
        )
        low_risk = self._clause(
            2,
            "The parties may exchange information from time to time as they consider appropriate.",
            obligations=[Obligation(subject="Parties", modal="may", polarity=Polarity.RIGHT,
                                     action="exchange information", confidence=0.8)],
        )
        operational = self._clause(
            3,
            "The Contractor shall comply with all applicable regulations and deliver the "
            "milestones within 30 days under the governing law and jurisdiction of Delaware.",
            deadlines=[Deadline(kind="duration", value="30 days")],
            legal_actions=[LegalAction(action_type="compliance", confidence=0.85)],
            jurisdiction="Delaware",
            obligations=[Obligation(subject="Contractor", modal="shall", polarity=Polarity.OBLIGATION,
                                     action="comply with regulations", confidence=0.9)],
        )

        result = self.engine.score_document([high_risk, low_risk, operational])

        self.assertEqual(len(result.clause_assessments), 3)
        by_id = {a.clause_id: a for a in result.clause_assessments}

        self.assertGreater(by_id[1].lrsi, by_id[2].lrsi)
        self.assertEqual(by_id[2].classification, "Low")

        # Financial should be the dominant contributor for clause 1.
        top_dimension = by_id[1].dimension_breakdown[0].dimension
        self.assertEqual(top_dimension, "Financial")
        self.assertTrue(any(by_id[1].dimension_breakdown[0].feature_evidence))

        # Entropy weights are a document-level property, shared by every
        # clause. Compared at 2 decimal places, not 4: dimension_weights'
        # values are each individually rounded to 4dp for display, so their
        # sum can drift a few ten-thousandths from the true (unrounded)
        # normalized total of 1.0 -- that's rounding, not a math error.
        self.assertAlmostEqual(sum(result.dimension_weights.values()), 1.0, places=2)
        for assessment in result.clause_assessments:
            self.assertEqual(len(assessment.dimension_breakdown), 5)
            self.assertGreaterEqual(assessment.confidence, 0.0)
            self.assertLessEqual(assessment.confidence, 100.0)

        self.assertEqual(
            result.high_count + result.medium_count + result.low_count,
            len(result.clause_assessments),
        )

    def test_empty_document_is_handled(self):
        result = self.engine.score_document([])
        self.assertEqual(result.clause_assessments, [])
        self.assertEqual(result.average_lrsi, 0.0)

    def test_dynamic_alpha_is_used_by_default_and_surfaced_in_output(self):
        clauses = [
            self._clause(
                i,
                f"Clause {i} shall pay a penalty of ${i * 1000}." if i % 2 == 0
                else f"Clause {i} discusses general administrative matters.",
                financial_terms=[FinancialTerm(amount=float(i * 1000))] if i % 2 == 0 else [],
            )
            for i in range(1, 9)
        ]
        result = self.engine.score_document(clauses)

        self.assertEqual(set(result.dimension_alphas.keys()), {"Financial", "Legal", "Compliance", "Operational", "Ambiguity"})
        for v in result.dimension_alphas.values():
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)

        first = result.clause_assessments[0].dimension_breakdown
        for dim in first:
            self.assertAlmostEqual(dim.alpha, result.dimension_alphas[dim.dimension], places=4)

        self.assertEqual(set(result.confidence_weights.keys()), {"agreement", "feature_confidence", "margin"})
        self.assertAlmostEqual(sum(result.confidence_weights.values()), 1.0, places=2)

    def test_alpha_override_pins_one_dimension_leaves_others_dynamic(self):
        clauses = [self._clause(i, f"Clause number {i}.") for i in range(1, 12)]
        engine = HybridExplainableRiskEngine(embed_fn=_fake_embed, alpha={"Financial": 0.1})
        result = engine.score_document(clauses)
        self.assertAlmostEqual(result.dimension_alphas["Financial"], 0.1, places=4)
        # Other dimensions weren't overridden, so nothing forces them to 0.5
        # or to 0.1 -- just confirm the registry actually varies per dimension
        # rather than every dimension collapsing to the same override value.
        self.assertFalse(all(v == 0.1 for k, v in result.dimension_alphas.items() if k != "Financial"))


if __name__ == "__main__":
    unittest.main()
