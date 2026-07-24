"""Tests for authenticity/clauses.py (Factor 2 of the Authenticity
Verification Engine) — tier-weighted mandatory clause-type completeness,
confidence discounting under type-classification uncertainty, and graceful
"not applicable" fallback for document types outside the mandatory-clause
registry.

Run with:  python -m unittest discover -s tests
"""

import unittest

from authenticity.clauses import assess_clause_completeness
from services.document_classifier import DocumentTypeClassification


def _clause(classification: str):
    return {"classification": classification, "text_content": f"{classification} clause text."}


class FullCompletenessTests(unittest.TestCase):
    def test_all_mandatory_types_present_scores_one(self):
        classification = DocumentTypeClassification(document_type="Loan Agreement", confidence=1.0)
        clauses = [_clause(t) for t in ["Payment", "Liability", "Jurisdiction", "Termination"]]
        result = assess_clause_completeness(clauses, classification)
        self.assertTrue(result.applicable)
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.missing_types, [])

    def test_evidence_lists_found_and_missing(self):
        classification = DocumentTypeClassification(document_type="Loan Agreement", confidence=1.0)
        clauses = [_clause("Payment")]
        result = assess_clause_completeness(clauses, classification)
        joined = " ".join(result.evidence)
        self.assertIn("Found: Payment", joined)
        self.assertIn("MISSING: Liability", joined)


class TierWeightingTests(unittest.TestCase):
    def test_missing_critical_tier_clause_hurts_more_than_missing_important_tier(self):
        # Employment Agreement mandatory set: Payment(Important,55),
        # Termination(Critical,80), Confidentiality(Important,55),
        # Compliance(Important,55). Missing the one Critical-tier entry
        # (Termination) should drop the score further than missing an
        # Important-tier entry (Compliance) of otherwise-identical count.
        classification = DocumentTypeClassification(document_type="Employment Agreement", confidence=1.0)

        missing_critical = [_clause(t) for t in ["Payment", "Confidentiality", "Compliance"]]
        missing_important = [_clause(t) for t in ["Payment", "Termination", "Confidentiality"]]

        result_missing_critical = assess_clause_completeness(missing_critical, classification)
        result_missing_important = assess_clause_completeness(missing_important, classification)

        self.assertLess(result_missing_critical.score, result_missing_important.score)

    def test_weighted_score_matches_closed_form(self):
        # Loan Agreement: Payment(55) + Liability(80) + Jurisdiction(80) + Termination(80) = 295 total.
        # Only Payment and Liability found -> (55+80)/295.
        classification = DocumentTypeClassification(document_type="Loan Agreement", confidence=1.0)
        clauses = [_clause("Payment"), _clause("Liability")]
        result = assess_clause_completeness(clauses, classification)
        expected = (55 + 80) / (55 + 80 + 80 + 80)
        self.assertAlmostEqual(result.score, expected, places=4)


class ConfidenceDiscountTests(unittest.TestCase):
    def test_low_type_confidence_discounts_but_does_not_change_required_set(self):
        clauses = [_clause(t) for t in ["Payment", "Liability", "Jurisdiction", "Termination"]]
        high_c = DocumentTypeClassification(document_type="Loan Agreement", confidence=1.0)
        low_c = DocumentTypeClassification(document_type="Loan Agreement", confidence=0.0)

        result_high = assess_clause_completeness(clauses, high_c)
        result_low = assess_clause_completeness(clauses, low_c)

        # Required/found/missing sets never change with confidence -- only
        # the reported confidence value does.
        self.assertEqual(result_high.required_types, result_low.required_types)
        self.assertEqual(result_high.score, result_low.score)
        self.assertLess(result_low.confidence, result_high.confidence)
        self.assertGreater(result_low.confidence, 0.0)  # floors at half strength, never zero when types were found


class NotApplicableTests(unittest.TestCase):
    def test_document_type_outside_registry_is_not_applicable(self):
        # Insurance Policy's real mandatory clauses (Coverage, Beneficiary)
        # aren't expressible in the 9 generic CLAUSE_RULES categories --
        # deliberately excluded from mandatory_clause_rules.json.
        classification = DocumentTypeClassification(document_type="Insurance Policy", confidence=1.0)
        result = assess_clause_completeness([_clause("Payment")], classification)
        self.assertFalse(result.applicable)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.confidence, 0.0)

    def test_unknown_document_type_is_not_applicable(self):
        classification = DocumentTypeClassification(document_type="Unknown Document", confidence=0.0)
        result = assess_clause_completeness([], classification)
        self.assertFalse(result.applicable)


if __name__ == "__main__":
    unittest.main()
