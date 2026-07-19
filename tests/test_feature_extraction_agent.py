"""Golden-set tests for agents/feature_extraction_agent.py — a small set of
hand-written clause sentences with known-correct obligation polarity,
financial terms, jurisdiction, and deadlines, the standard way to validate
a rule/parse-based extractor absent a labeled legal dataset.

Run with:  python -m unittest discover -s tests
"""

import unittest

from agents.feature_extraction_agent import (
    _evidence_confidence,
    _regex_corroborates_subject,
    extract_deadlines,
    extract_entities,
    extract_financial_terms,
    extract_jurisdiction,
    extract_legal_actions,
    extract_legal_features,
    extract_legal_features_batch,
    extract_obligations,
    _get_nlp,
)
from risk_engine.schemas import Polarity


class ObligationExtractionTests(unittest.TestCase):
    def test_strong_modal_is_obligation(self):
        doc = _get_nlp()(
            "The Vendor shall indemnify and hold harmless the Client from any "
            "third-party claims arising from a breach of this Agreement."
        )
        obligations = extract_obligations(doc)
        self.assertGreaterEqual(len(obligations), 1)
        self.assertEqual(obligations[0].polarity, Polarity.OBLIGATION)
        self.assertIn("Vendor", obligations[0].subject)
        self.assertEqual(obligations[0].modal.lower(), "shall")

    def test_negated_strong_modal_is_prohibition(self):
        doc = _get_nlp()(
            "The Contractor shall not disclose Confidential Information to any "
            "third party without prior written consent."
        )
        obligations = extract_obligations(doc)
        self.assertGreaterEqual(len(obligations), 1)
        self.assertEqual(obligations[0].polarity, Polarity.PROHIBITION)
        self.assertIn("Contractor", obligations[0].subject)

    def test_weak_modal_is_right(self):
        doc = _get_nlp()("Either party may terminate this Agreement upon 30 days written notice.")
        obligations = extract_obligations(doc)
        self.assertGreaterEqual(len(obligations), 1)
        self.assertEqual(obligations[0].polarity, Polarity.RIGHT)
        self.assertEqual(obligations[0].modal.lower(), "may")

    def test_coordinated_clauses_each_get_their_own_obligation(self):
        # Regression test: a coordinated "X shall A and shall not B and
        # shall C" sentence originally produced exactly one Obligation
        # whose action text merged every conjunct's words together and
        # silently dropped the word "not" (its dep_=='neg' tag was filtered
        # globally, not scoped to the clause it belonged to) — so a clause
        # literally stating unlimited, uncapped liability read as capped.
        doc = _get_nlp()(
            "The Company's liability under this Agreement shall be unlimited and shall "
            "not be subject to any cap, and shall apply immediately upon breach."
        )
        obligations = extract_obligations(doc)
        self.assertEqual(len(obligations), 3)
        polarities = [o.polarity for o in obligations]
        self.assertIn(Polarity.PROHIBITION, polarities)

        capped_obligation = next(o for o in obligations if o.polarity == Polarity.PROHIBITION)
        self.assertIn("subject to any cap", capped_obligation.action)
        self.assertNotIn(" not ", f" {capped_obligation.action} ")  # negation lives in polarity, not the text
        for o in obligations:
            self.assertIn("liability", o.subject.lower())


class FinancialExtractionTests(unittest.TestCase):
    def test_capped_amount_detected(self):
        terms = extract_financial_terms("Total liability shall be capped at $500,000 for any single claim.")
        self.assertEqual(len(terms), 1)
        self.assertAlmostEqual(terms[0].amount, 500000.0)
        self.assertEqual(terms[0].currency, "USD")
        self.assertFalse(terms[0].is_percentage)
        self.assertTrue(terms[0].is_capped)

    def test_percentage_detected(self):
        terms = extract_financial_terms("A late fee of 5% per month applies to overdue invoices.")
        self.assertEqual(len(terms), 1)
        self.assertTrue(terms[0].is_percentage)
        self.assertAlmostEqual(terms[0].amount, 5.0)

    def test_qualitative_uncapped_language_without_a_figure_yields_no_financial_term(self):
        # Known, accepted hybrid-design property: with no numeric figure at
        # all, the regex-based money extractor correctly finds nothing —
        # this is exactly the case the *semantic* branch (embedding
        # similarity to the "unlimited financial exposure" prototype in
        # risk_engine/prototypes.json) is there to catch instead. Not a bug.
        terms = extract_financial_terms(
            "The Company's liability under this Agreement shall be unlimited "
            "and shall not be subject to any cap."
        )
        self.assertEqual(terms, [])


class DeadlineExtractionTests(unittest.TestCase):
    def test_duration_normalized_to_days(self):
        deadlines = extract_deadlines("Either party may terminate this Agreement upon 30 days written notice.")
        durations = [d for d in deadlines if d.kind == "duration"]
        self.assertEqual(len(durations), 1)
        self.assertAlmostEqual(durations[0].normalized_days, 30.0)


class JurisdictionExtractionTests(unittest.TestCase):
    def test_governing_law_clause(self):
        jurisdiction = extract_jurisdiction("This Agreement shall be governed by the laws of the State of Delaware.")
        self.assertIsNotNone(jurisdiction)
        self.assertIn("Delaware", jurisdiction)

    def test_no_jurisdiction_language_returns_none(self):
        self.assertIsNone(extract_jurisdiction("The parties may exchange information from time to time."))


class LegalActionExtractionTests(unittest.TestCase):
    def test_indemnification_detected_via_phrase_and_lemma(self):
        doc = _get_nlp()("The Vendor shall indemnify and hold harmless the Client from any claims.")
        actions = {a.action_type for a in extract_legal_actions(doc)}
        self.assertIn("indemnification", actions)

    def test_termination_detected(self):
        doc = _get_nlp()("Either party may terminate this Agreement upon 30 days written notice.")
        actions = {a.action_type for a in extract_legal_actions(doc)}
        self.assertIn("termination", actions)


class EntityExtractionTests(unittest.TestCase):
    def test_defined_party_detected(self):
        doc = _get_nlp()(
            'This Agreement is entered into between Acme Corporation ("Vendor") '
            'and Beta LLC ("Client").'
        )
        entities = extract_entities(doc)
        party_names = {e.text for e in entities if e.entity_type == "PARTY"}
        self.assertTrue({"Vendor", "Client"} <= party_names)


class SingleClauseIntegrationTest(unittest.TestCase):
    def test_extract_legal_features_populates_every_field_type(self):
        fv = extract_legal_features(
            1,
            "The Vendor shall indemnify and hold harmless the Client for any "
            "damages up to a cap of $1,000,000, governed by the laws of the "
            "State of New York, within 15 days of written notice.",
        )
        self.assertEqual(fv.clause_id, 1)
        self.assertTrue(fv.obligations)
        self.assertTrue(fv.financial_terms)
        self.assertTrue(fv.deadlines)
        self.assertIsNotNone(fv.jurisdiction)
        self.assertTrue(fv.legal_actions)


class BatchDependencyResolutionTest(unittest.TestCase):
    def test_explicit_cross_reference_becomes_a_dependency(self):
        clauses = [
            {"id": 1, "section_name": "5.2 Indemnification", "text_content":
                "The Vendor shall indemnify the Client for any losses.", "classification": "Indemnity"},
            {"id": 2, "section_name": "7.1 Limitation of Liability", "text_content":
                "Notwithstanding Section 5.2, total liability shall be capped at $500,000.",
             "classification": "Liability"},
        ]
        feature_vectors = extract_legal_features_batch(clauses)
        by_id = {fv.clause_id: fv for fv in feature_vectors}
        self.assertEqual(len(by_id[2].dependencies), 1)
        self.assertEqual(by_id[2].dependencies[0].target_clause_id, 1)
        # Unambiguous: only one clause is numbered "5.2" -> corroborated -> higher confidence.
        self.assertAlmostEqual(by_id[2].dependencies[0].confidence, 2 / 3, places=4)

    def test_ambiguous_section_number_gets_lower_confidence(self):
        clauses = [
            {"id": 1, "section_name": "5.2 Indemnification", "text_content":
                "The Vendor shall indemnify the Client for any losses.", "classification": "Indemnity"},
            {"id": 2, "section_name": "5.2 Duplicate Heading", "text_content":
                "A second, differently-worded clause that also happens to be numbered 5.2.",
             "classification": "General"},
            {"id": 3, "section_name": "7.1 Limitation of Liability", "text_content":
                "Notwithstanding Section 5.2, total liability shall be capped at $500,000.",
             "classification": "Liability"},
        ]
        feature_vectors = extract_legal_features_batch(clauses)
        by_id = {fv.clause_id: fv for fv in feature_vectors}
        self.assertEqual(len(by_id[3].dependencies), 1)
        # Two clauses share the number "5.2" -> the resolution could have
        # picked the wrong one -> no corroboration bonus.
        self.assertAlmostEqual(by_id[3].dependencies[0].confidence, 0.5, places=4)


class EvidenceConfidenceTests(unittest.TestCase):
    def test_single_detector_baseline(self):
        self.assertAlmostEqual(_evidence_confidence(1), 0.5)

    def test_two_agreeing_detectors_score_higher(self):
        self.assertAlmostEqual(_evidence_confidence(2), 2 / 3)
        self.assertGreater(_evidence_confidence(2), _evidence_confidence(1))

    def test_monotonically_increasing_and_bounded_below_one(self):
        values = [_evidence_confidence(n) for n in range(1, 10)]
        self.assertEqual(values, sorted(values))
        self.assertTrue(all(v < 1.0 for v in values))

    def test_regex_corroboration_matches_similar_subject(self):
        regex_hits = [("The Vendor", "shall", "pay the invoice")]
        self.assertTrue(_regex_corroborates_subject("The Vendor", regex_hits))
        self.assertTrue(_regex_corroborates_subject("Vendor", regex_hits))  # loose fuzzy match
        self.assertFalse(_regex_corroborates_subject("A wholly unrelated corporate entity", regex_hits))

    def test_regex_corroboration_empty_hits(self):
        self.assertFalse(_regex_corroborates_subject("Anything", []))


class LegalActionConfidenceTests(unittest.TestCase):
    def test_two_independent_routes_score_higher_than_one(self):
        # "hold harmless" (phrase route) + "indemnify" (lemma route) both
        # independently map to "indemnification" in this single sentence.
        both_routes = _get_nlp()("The Vendor shall indemnify and hold harmless the Client.")
        one_route = _get_nlp()("The Vendor shall indemnify the Client.")

        both_actions = {a.action_type: a.confidence for a in extract_legal_actions(both_routes)}
        one_action = {a.action_type: a.confidence for a in extract_legal_actions(one_route)}

        self.assertIn("indemnification", both_actions)
        self.assertIn("indemnification", one_action)
        self.assertGreater(both_actions["indemnification"], one_action["indemnification"])
        self.assertAlmostEqual(one_action["indemnification"], 0.5)
        self.assertAlmostEqual(both_actions["indemnification"], 2 / 3)


if __name__ == "__main__":
    unittest.main()
