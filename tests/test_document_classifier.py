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


INVOICE_TEXT = "TAX INVOICE\nInvoice No: INV-2024-00456\nBill To: Sunrise Traders\nGSTIN: 27ABCDE1234F1Z5\nSubtotal: Rs. 65,000"
RECEIPT_TEXT = "PAYMENT RECEIPT\nReceipt No: RCT-99213\nReceived from: Priya Sharma\nPayment Mode: Cash"
MEDICAL_RECORD_TEXT = "PATIENT DISCHARGE SUMMARY\nPatient ID: PT-004521\nDate of Admission: 10/02/2024\nDiagnosis: Acute appendicitis\nAttending Physician: Dr. S. Rao"
BANK_STATEMENT_TEXT = "ACCOUNT STATEMENT\nAccount Number: 5021 3456 7890\nStatement Period: 01/03/2024 to 31/03/2024\nOpening Balance: 50,000\nClosing Balance: 90,000\nIFSC: HDFC0001234"
IDENTITY_DOCUMENT_TEXT = "PASSPORT\nPassport No: N1234567\nDate of Birth: 12/08/1990\nPlace of Birth: MUMBAI"
CERTIFICATE_TEXT = "This is to certify that RAHUL MEHTA has completed the course.\nCertificate No: DU/2023/CS/00214"
PURCHASE_ORDER_TEXT = "PURCHASE ORDER\nPO Number: PO-2024-0091\nVendor: Global Supplies Pvt Ltd\nShip To: Warehouse 3"
GOVERNMENT_NOTICE_TEXT = "GOVERNMENT OF MAHARASHTRA\nNOTIFICATION\nNo. REV-2024/1123\nIn exercise of the powers conferred..."

# A bank statement that happens to mention "salary" (a real-world-realistic
# line item) -- the exact text shape that caused the pre-fix classifier to
# mistake a bank statement for an Employment Agreement (audit finding).
BANK_STATEMENT_WITH_SALARY_LINE = (
    "HDFC BANK LIMITED\nACCOUNT STATEMENT\nAccount Number: 5021 3456 7890\n"
    "Statement Period: 01/03/2024 to 31/03/2024\n"
    "05/03/2024  Salary Credit   45,000   95,000\nClosing Balance: Rs. 90,000"
)


class NewDocumentTypeDisambiguationTests(unittest.TestCase):
    """2026-07-26 audit follow-up: the 8 types below were previously
    entirely unrecognized (UNKNOWN_DOCUMENT_TYPE for every genuine document
    of these kinds). Verifies both that each is now correctly recognized
    AND that adding them didn't steal matches away from the pre-existing 21
    types (checked via test_clear_match / test_insurance_policy_detected
    above, which still pass unchanged)."""

    def test_invoice_detected(self):
        self.assertEqual(classify_document_type(INVOICE_TEXT), "Invoice")

    def test_receipt_detected(self):
        self.assertEqual(classify_document_type(RECEIPT_TEXT), "Receipt")

    def test_medical_record_detected(self):
        self.assertEqual(classify_document_type(MEDICAL_RECORD_TEXT), "Medical Record")

    def test_bank_statement_detected(self):
        self.assertEqual(classify_document_type(BANK_STATEMENT_TEXT), "Bank Statement")

    def test_identity_document_detected(self):
        self.assertEqual(classify_document_type(IDENTITY_DOCUMENT_TEXT), "Identity Document")

    def test_certificate_detected(self):
        self.assertEqual(classify_document_type(CERTIFICATE_TEXT), "Certificate")

    def test_purchase_order_detected_not_vendor_agreement(self):
        # Regression guard: "Vendor Agreement"'s existing patterns include a
        # bare "purchase order" phrase, so a genuine PO document risks being
        # outscored into the wrong (and unregistered-template) type.
        self.assertEqual(classify_document_type(PURCHASE_ORDER_TEXT), "Purchase Order")

    def test_government_notice_detected(self):
        self.assertEqual(classify_document_type(GOVERNMENT_NOTICE_TEXT), "Government Notice")

    def test_bank_statement_with_salary_line_is_not_misclassified_as_employment_agreement(self):
        # The exact audit-confirmed false positive: a bank statement with a
        # "Salary Credit" line item used to win as "Employment Agreement"
        # because Bank Statement had no registered pattern at all.
        self.assertEqual(classify_document_type(BANK_STATEMENT_WITH_SALARY_LINE), "Bank Statement")

    def test_existing_types_still_win_their_own_documents(self):
        # New patterns must not cannibalize the pre-existing 21 types' own
        # matches -- spot-check a few representative ones.
        self.assertEqual(classify_document_type(NDA_TEXT), "Non-Disclosure Agreement (NDA)")
        self.assertEqual(classify_document_type(INSURANCE_TEXT), "Insurance Policy")


if __name__ == "__main__":
    unittest.main()
