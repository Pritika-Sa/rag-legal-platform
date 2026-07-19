"""End-to-end integration test for agents/analyzer_agent.assess_clauses_batch
— the function that replaced the old per-clause analyze_clause()/
score_risk_points() keyword scorer in agents/orchestrator.py. Unlike
tests/test_risk_engine.py (fake embeddings) and tests/test_feature_extraction_agent.py
(spaCy only), this exercises the real pipeline: spaCy NER/dependency parsing
+ the real sentence-transformer embedding model + entropy-weighted fusion,
on clause text shaped like what agents/orchestrator.py actually passes in
(dicts with 'section_name'/'text_content', no pre-existing 'id').

Slower than the other suites (loads the real embedding model) — run with:
  python -m unittest tests.test_analyzer_agent_integration
"""

import unittest

from agents.analyzer_agent import assess_clauses_batch


class AssessClausesBatchIntegrationTest(unittest.TestCase):
    def test_realistic_document_ranks_and_persists_shape_correctly(self):
        clauses = [
            {"section_name": "5.2 Indemnification", "text_content":
                "The Vendor shall indemnify and hold harmless the Client for any damages up to a "
                "cap of $1,000,000, governed by the laws of the State of New York, within 15 days "
                "of written notice."},
            {"section_name": "7.1 Liability", "text_content":
                "The Company's liability under this Agreement shall be unlimited and shall not be "
                "subject to any cap, and shall apply immediately upon breach."},
            {"section_name": "9.3 General", "text_content":
                "The parties may exchange information from time to time as they consider appropriate."},
        ]

        results, document_assessment = assess_clauses_batch(clauses)

        self.assertEqual(len(results), 3)
        # No caller-visible 'id' requirement — orchestrator calls this
        # before clause database ids are assigned.
        for c in clauses:
            self.assertNotIn("id", c)

        for result in results:
            self.assertIn(result.risk_level, ("Low", "Medium", "High"))
            self.assertTrue(0 <= result.risk_score <= 100)
            self.assertTrue(0 <= result.confidence <= 100)
            self.assertEqual(len(result.dimension_breakdown), 5)
            self.assertIn(result.risk_category, ("Financial", "Legal", "Compliance", "Operational", "Ambiguity"))
            self.assertTrue(result.explanation)
            # ClauseAnalysisResult stays a valid contract for crud.add_clauses_bulk:
            # every dimension entry round-trips to a plain dict (MongoDB-safe).
            for dim in result.dimension_breakdown:
                dumped = dim.model_dump()
                self.assertIn("dimension", dumped)
                self.assertIn("contribution", dumped)

        self.assertAlmostEqual(sum(document_assessment.dimension_weights.values()), 1.0, places=4)
        self.assertEqual(
            document_assessment.high_count + document_assessment.medium_count + document_assessment.low_count,
            3,
        )

        # The unlimited/uncapped liability clause should not be out-ranked by
        # vague, low-content boilerplate — a real bug caught during manual
        # smoke testing (dropped negation in coordinated obligation
        # extraction, then small-n entropy-weight instability) before this
        # test existed.
        by_section = {c["section_name"]: r for c, r in zip(clauses, results)}
        self.assertGreaterEqual(
            by_section["7.1 Liability"].risk_score,
            by_section["9.3 General"].risk_score,
        )

    def test_empty_clause_list(self):
        results, document_assessment = assess_clauses_batch([])
        self.assertEqual(results, [])
        self.assertEqual(document_assessment.clause_assessments, [])


if __name__ == "__main__":
    unittest.main()
