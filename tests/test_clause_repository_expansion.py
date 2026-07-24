import unittest

from agents.rule_engine import CLAUSE_RULES, detect_clause_type
from agents.clause_explainability import explain_clause_detection, detect_clause_types_multilabel


class SchemaTests(unittest.TestCase):
    def test_every_category_has_keywords_and_regex(self):
        for clause_type, rules in CLAUSE_RULES.items():
            self.assertIn("keywords", rules, clause_type)
            self.assertIn("regex", rules, clause_type)
            self.assertIsInstance(rules["keywords"], list)
            self.assertGreater(len(rules["keywords"]), 0, clause_type)
            self.assertIsInstance(rules["regex"], str)
            self.assertGreater(len(rules["regex"]), 0, clause_type)

    def test_total_category_count_is_comprehensive(self):
        self.assertGreaterEqual(len(CLAUSE_RULES), 40)


class BackwardCompatibilityTests(unittest.TestCase):
    """The original 9 categories must still win on their canonical phrasing."""

    ORIGINAL_SAMPLES = {
        "Termination": "Either party may terminate this Agreement upon material breach if not cured within 30 days after written notice.",
        "Liability": "In no event shall either party's liability exceed the limitation of liability cap, and neither party shall be liable for consequential damages.",
        "Confidentiality": "Each party shall treat all confidential information disclosed under this non-disclosure agreement as strictly confidential.",
        "Arbitration": "Any dispute shall be resolved by binding arbitration administered by the AAA, and the decision of the arbitrator shall be final.",
        "Payment": "Invoices are due within thirty (30) days of the invoice date; late payment shall accrue interest on the outstanding balance.",
        "Indemnity": "The Contractor shall indemnify, defend, and hold harmless the Client from all third-party claims and losses.",
        "Compliance": "Each party shall comply with all applicable laws and regulations, including anti-corruption and sanctions requirements.",
        "Jurisdiction": "This Agreement shall be governed by the laws of the State of Delaware, and the parties submit to the exclusive jurisdiction of its courts.",
        "Force Majeure": "Neither party shall be liable for delay caused by force majeure events, including acts of God or natural disaster beyond its reasonable control.",
    }

    def test_original_categories_still_detected(self):
        for expected_type, text in self.ORIGINAL_SAMPLES.items():
            with self.subTest(clause_type=expected_type):
                detected_type, confidence = detect_clause_type(text)
                self.assertEqual(detected_type, expected_type)
                self.assertGreater(confidence, 0.0)


class NewCategoryCoverageTests(unittest.TestCase):
    NEW_SAMPLES = {
        "Coverage and Scope": "This policy provides coverage for covered losses up to the policy limits stated in the schedule.",
        "Premium": "The Insured shall pay the annual premium in full before the policy's grace period expires.",
        "Deductible and Exclusions": "Claims are subject to a $1,000 deductible, and losses arising from war are excluded under the policy exclusions.",
        "Beneficiary Designation": "The Policyholder may change the named beneficiary at any time by written notice to the Insurer.",
        "Compensation and Benefits": "Employee shall receive an annual salary of $95,000, payable in accordance with the Company's standard payroll practices, plus employee benefits.",
        "Restrictive Covenants": "During employment and for twelve months thereafter, Employee agrees to a non-compete and shall not solicit employees of the Company.",
        "Rent and Lease Payments": "Tenant shall pay monthly rent of $2,500, due on the first day of each calendar month.",
        "Security Deposit": "Landlord shall hold a security deposit of one month's rent, refundable upon return of the deposit at lease end.",
        "Delivery and Risk of Loss": "Risk of loss passes to Buyer upon delivery of the goods FOB the seller's shipping dock.",
        "Interest and Fees": "The Loan bears a default interest rate of 6% per annum, and any late fee shall accrue as penalty interest on overdue installments.",
        "Collateral and Security Interest": "Borrower grants Lender a security interest in the Collateral, which shall not be subject to any other lien or encumbrance.",
        "Events of Default": "Upon an Event of Default, including any cross-default under other indebtedness, the Lender may accelerate all amounts due.",
        "Capital Contribution": "Each Partner shall make an initial capital contribution as reflected in their capital account.",
        "Profit and Loss Allocation": "Profits and losses shall be allocated among the Partners in proportion to their respective partnership interests.",
        "Intellectual Property": "All intellectual property, including copyright and trademark rights in the work product, shall vest in the Company.",
        "Data Protection": "Each party shall comply with applicable data protection laws with respect to any personal data processed under this Agreement.",
    }

    def test_new_categories_detected(self):
        for expected_type, text in self.NEW_SAMPLES.items():
            with self.subTest(clause_type=expected_type):
                detected_type, confidence = detect_clause_type(text)
                self.assertEqual(detected_type, expected_type)
                self.assertGreater(confidence, 0.0)


class ExplainabilityTests(unittest.TestCase):
    def test_explain_clause_detection_returns_full_trace(self):
        text = "Tenant shall pay monthly rent of $2,500, due on the first day of each calendar month."
        result = explain_clause_detection(text)
        self.assertEqual(result["clause_type"], "Rent and Lease Payments")
        self.assertGreater(len(result["matched_keywords"]), 0)
        self.assertIsNotNone(result["matched_regex"])
        self.assertIsNotNone(result["regex_pattern"])
        self.assertIn("Rent and Lease Payments", result["reason"])

    def test_explain_clause_detection_handles_no_match(self):
        result = explain_clause_detection("The sky is blue and the weather is nice today.")
        self.assertEqual(result["clause_type"], "General")
        self.assertEqual(result["matched_keywords"], [])
        self.assertIsNone(result["matched_regex"])


class MultiLabelDetectionTests(unittest.TestCase):
    def test_clause_with_two_concepts_returns_both_labels(self):
        text = (
            "If Client fails to make payment of the outstanding invoice within thirty (30) days "
            "of the due date, Provider may terminate this Agreement upon written notice of such breach."
        )
        results = detect_clause_types_multilabel(text)
        detected_types = {r["clause_type"] for r in results}
        self.assertIn("Payment", detected_types)
        self.assertIn("Termination", detected_types)

    def test_confidentiality_and_indemnity_clause_returns_both_labels(self):
        text = (
            "The Receiving Party shall keep all confidential information strictly confidential and "
            "shall indemnify and hold harmless the Disclosing Party against any losses arising from "
            "unauthorized disclosure of trade secrets."
        )
        results = detect_clause_types_multilabel(text)
        detected_types = {r["clause_type"] for r in results}
        self.assertIn("Confidentiality", detected_types)
        self.assertIn("Indemnity", detected_types)

    def test_results_sorted_by_confidence_descending(self):
        text = (
            "If Client fails to make payment of the outstanding invoice within thirty (30) days "
            "of the due date, Provider may terminate this Agreement upon written notice of such breach."
        )
        results = detect_clause_types_multilabel(text)
        confidences = [r["confidence"] for r in results]
        self.assertEqual(confidences, sorted(confidences, reverse=True))

    def test_each_result_has_full_explainability_fields(self):
        text = (
            "If Client fails to make payment of the outstanding invoice within thirty (30) days "
            "of the due date, Provider may terminate this Agreement upon written notice of such breach."
        )
        results = detect_clause_types_multilabel(text)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn("clause_type", r)
            self.assertIn("confidence", r)
            self.assertIn("matched_keywords", r)
            self.assertIn("matched_regex", r)
            self.assertIn("regex_pattern", r)
            self.assertIn("reason", r)
            self.assertGreater(len(r["matched_keywords"]) + (1 if r["matched_regex"] else 0), 0)

    def test_no_match_returns_empty_list(self):
        results = detect_clause_types_multilabel("The sky is blue and the weather is nice today.")
        self.assertEqual(results, [])

    def test_multilabel_agrees_with_single_label_winner(self):
        """Whenever detect_clause_type's winner clears the multi-label
        confidence bar, it must appear in the multi-label results as the top
        (or tied-for-top) entry -- multi-label is a superset of single-label,
        never a contradiction. (detect_clause_type itself has no confidence
        floor, so a low-confidence single-label "best guess" below the
        multi-label threshold is correctly absent from the multi-label list;
        that's the whole point of the threshold.)"""
        all_samples = {**BackwardCompatibilityTests.ORIGINAL_SAMPLES, **NewCategoryCoverageTests.NEW_SAMPLES}
        for expected_type, text in all_samples.items():
            with self.subTest(clause_type=expected_type):
                single_type, single_confidence = detect_clause_type(text)
                results = detect_clause_types_multilabel(text)
                by_type = {r["clause_type"]: r["confidence"] for r in results}
                if single_confidence < 0.3:
                    continue  # below the multi-label bar by design; nothing to compare
                self.assertIn(single_type, by_type)
                self.assertAlmostEqual(by_type[single_type], single_confidence, places=2)
                self.assertEqual(by_type[single_type], max(by_type.values()))

    def test_single_concept_clause_still_returns_one_dominant_label(self):
        """Guards against over-eager multi-labeling: an unambiguous single-
        concept clause should not spuriously pick up unrelated categories."""
        text = "This Agreement shall be governed by the laws of the State of Delaware, and the parties submit to the exclusive jurisdiction of its courts."
        results = detect_clause_types_multilabel(text)
        detected_types = [r["clause_type"] for r in results]
        self.assertIn("Jurisdiction", detected_types)
        self.assertEqual(results[0]["clause_type"], "Jurisdiction")


if __name__ == "__main__":
    unittest.main()
