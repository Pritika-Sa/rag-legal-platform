"""End-to-end integration test for agents/authenticity_agent.py's live
assess_document_authenticity() — the function agents/orchestrator.py's
authenticity_check_node actually calls. Unlike the individual
tests/test_authenticity_*.py suites (each factor in isolation), this
exercises the real orchestration: Stage 0 classification -> all 7 factors
-> authenticity.dai fusion, on clause data shaped like what
agents/orchestrator.py actually passes in.

No file_path/pages are passed here (mirrors a live DOCX upload, where
pages=[] and the .docx extension makes digital/metadata not-applicable
anyway) -- exercises the "some factors not applicable" partial-fusion path
that a real upload commonly hits. The PDF-specific factors (digital,
metadata) and the multi-page factor (entity_verification) already have
their own real-fixture integration tests in test_authenticity_digital.py /
test_authenticity_metadata.py / test_authenticity_entities.py; this test's
job is only to prove the orchestration layer wires all 7 together
correctly, not to re-prove each factor's own logic.

Run with:  python -m unittest tests.test_authenticity_agent_integration
"""

import unittest

from agents.authenticity_agent import assess_document_authenticity
from authenticity.dai import DAI_TIER_LABELS

LOAN_AGREEMENT_TEXT = """
LOAN AGREEMENT

This Loan Agreement is entered into between First National Bank ("Lender") and John Doe ("Borrower") on January 1, 2024.

1. Principal Amount
The principal amount of this loan is Rs. 5,00,000, disbursed upon execution of this Agreement.

2. Repayment Terms
The Borrower shall repay the principal amount of Rs. 5,00,000 in 24 equal monthly installments.

3. Interest Rate
The rate of interest applicable to this loan shall be 8% per annum.

4. Governing Law
This Agreement shall be governed by the laws of the State of New York.

5. Termination
This Agreement may be terminated upon full repayment of all amounts due.

Signature: ___________________
Authorized Signatory
Dated: January 1, 2024
"""

LOAN_AGREEMENT_CLAUSES = [
    {"section_name": "1. Principal Amount", "classification": "General", "text_content":
        "The principal amount of this loan is Rs. 5,00,000, disbursed upon execution of this Agreement."},
    {"section_name": "2. Repayment Terms", "classification": "Payment", "text_content":
        "The Borrower shall repay the principal amount of Rs. 5,00,000 in 24 equal monthly installments."},
    {"section_name": "3. Interest Rate", "classification": "Payment", "text_content":
        "The rate of interest applicable to this loan shall be 8% per annum."},
    {"section_name": "4. Governing Law", "classification": "Jurisdiction", "text_content":
        "This Agreement shall be governed by the laws of the State of New York."},
    {"section_name": "5. Termination", "classification": "Termination", "text_content":
        "This Agreement may be terminated upon full repayment of all amounts due."},
]

JUNK_TEXT = "The quick brown fox jumps over the lazy dog near the river bank on a sunny afternoon."
JUNK_CLAUSES = [
    {"section_name": "para 1", "classification": "General", "text_content": JUNK_TEXT},
]


class AssessDocumentAuthenticityIntegrationTest(unittest.TestCase):
    def test_realistic_loan_agreement_produces_a_valid_shaped_result(self):
        result = assess_document_authenticity("loan.pdf", LOAN_AGREEMENT_CLAUSES, LOAN_AGREEMENT_TEXT)

        self.assertTrue(0 <= result.authenticity_score <= 100)
        self.assertIn(result.authenticity_level, DAI_TIER_LABELS + ("Insufficient Signal",))
        self.assertEqual(result.document_type, "Loan Agreement")
        self.assertEqual(len(result.factors), 8)

        by_name = {f.name: f for f in result.factors}
        # No file_path/pages were passed -- mirrors a live DOCX upload.
        self.assertFalse(by_name["digital_verification"].applicable)
        self.assertFalse(by_name["metadata_validation"].applicable)
        self.assertFalse(by_name["entity_verification"].applicable)
        # Loan Agreement has no registered document-type-specific validator.
        self.assertFalse(by_name["document_type_validator"].applicable)
        # These four don't need the raw file, so they should have run.
        self.assertTrue(by_name["structure"].applicable)
        self.assertTrue(by_name["clause_completeness"].applicable)
        self.assertTrue(by_name["cross_field"].applicable)
        self.assertTrue(by_name["semantic_consistency"].applicable)

        # Applicable factors' weights should sum to ~1; inapplicable ones report no weight.
        applicable_weights = [f.weight for f in result.factors if f.applicable]
        self.assertAlmostEqual(sum(applicable_weights), 1.0, places=2)
        for f in result.factors:
            if not f.applicable:
                self.assertIsNone(f.weight)
                self.assertIsNone(f.score)

    def test_well_formed_document_scores_higher_than_unstructured_junk_text(self):
        loan_result = assess_document_authenticity("loan.pdf", LOAN_AGREEMENT_CLAUSES, LOAN_AGREEMENT_TEXT)
        junk_result = assess_document_authenticity("junk.pdf", JUNK_CLAUSES, JUNK_TEXT)
        self.assertGreater(loan_result.authenticity_score, junk_result.authenticity_score)
        self.assertEqual(junk_result.document_type, "Unknown Document")

    def test_missing_clause_fields_do_not_crash_the_whole_assessment(self):
        malformed_clauses = [{"section_name": None, "text_content": None}]
        result = assess_document_authenticity("malformed.pdf", malformed_clauses, "some text")
        self.assertEqual(len(result.factors), 8)
        self.assertTrue(0 <= result.authenticity_score <= 100)


if __name__ == "__main__":
    unittest.main()
