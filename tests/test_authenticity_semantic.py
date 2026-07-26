"""Tests for authenticity/semantic.py (Factor 7 of the Authenticity
Verification Engine) — real embedding-model heading-vs-body cosine
similarity (no mocking, same real-model precedent as
test_authenticity_entities.py), and graceful non-applicability when no
clause has both a heading and body.

Run with:  python -m unittest discover -s tests
"""

import unittest

from authenticity.semantic import _calibrate_similarity, assess_semantic_consistency

MATCHED_CLAUSE = {
    "section_name": "Termination",
    "text_content": (
        "Either party may terminate this Agreement upon thirty (30) days' written notice "
        "to the other party in the event of a material breach that remains uncured."
    ),
}

MISMATCHED_CLAUSE = {
    "section_name": "Payment",
    "text_content": (
        "Arctic terns undertake the longest migration of any known animal, travelling "
        "from their Arctic breeding grounds to the Antarctic and back each year."
    ),
}

# A table-row-style "clause" from a scanned insurance policy: a field label
# next to a bare code, not prose. Regression fixture for the false-positive
# this factor originally raised -- cosine similarity between a heading and
# a non-language code is near zero by construction, not because anything
# was tampered with.
TABLE_ROW_CLAUSE = {
    "section_name": "Engine Number",
    "text_content": "ABCD1234EFGH",
}


class HeadingBodyMatchTests(unittest.TestCase):
    def test_well_matched_clause_scores_higher_than_mismatched_one(self):
        matched_result = assess_semantic_consistency([MATCHED_CLAUSE])
        mismatched_result = assess_semantic_consistency([MISMATCHED_CLAUSE])
        self.assertTrue(matched_result.applicable)
        self.assertTrue(mismatched_result.applicable)
        self.assertGreater(matched_result.score, mismatched_result.score)

    def test_document_score_is_mean_of_calibrated_clause_similarities(self):
        # 2026-07-26 audit follow-up: `checked[i].similarity` reports the
        # RAW cosine similarity (honest, directly-interpretable per-clause
        # evidence); the factor SCORE is the mean of the CALIBRATED values
        # (see authenticity/semantic.py's SEMANTIC_SIMILARITY_FLOOR/CEILING)
        # so it's on the same 0-1 "authenticity fraction" scale as the other
        # 7 factors, not raw embedding-model output.
        result = assess_semantic_consistency([MATCHED_CLAUSE, MISMATCHED_CLAUSE])
        expected = round(
            sum(_calibrate_similarity(c.similarity) for c in result.checked) / len(result.checked), 4,
        )
        self.assertAlmostEqual(result.score, expected, places=4)

    def test_calibration_maps_a_genuinely_matched_clause_near_the_top(self):
        # Regression for the actual audit finding: two real, complete,
        # correctly-clause-tagged genuine documents (a Loan Agreement and an
        # NDA) scored raw mean similarity 0.45-0.49 during the audit --
        # nowhere near 1.0 despite being genuinely well-formed, dragging
        # their overall DAI score down. A clearly matched pair's calibrated
        # score must now read as strongly consistent, not middling.
        result = assess_semantic_consistency([MATCHED_CLAUSE])
        self.assertGreaterEqual(result.score, 0.9)

    def test_evidence_names_the_lowest_matching_clause(self):
        result = assess_semantic_consistency([MATCHED_CLAUSE, MISMATCHED_CLAUSE])
        joined = " ".join(result.evidence)
        self.assertIn("Payment", joined)


class NotApplicableTests(unittest.TestCase):
    def test_empty_clause_list_is_not_applicable(self):
        result = assess_semantic_consistency([])
        self.assertFalse(result.applicable)

    def test_clauses_missing_heading_or_body_are_excluded(self):
        result = assess_semantic_consistency([
            {"section_name": "", "text_content": "some body text"},
            {"section_name": "Some Heading", "text_content": "  "},
        ])
        self.assertFalse(result.applicable)

    def test_mixed_usable_and_unusable_clauses_only_checks_usable_ones(self):
        result = assess_semantic_consistency([MATCHED_CLAUSE, {"section_name": "", "text_content": "x"}])
        self.assertTrue(result.applicable)
        self.assertEqual(len(result.checked), 1)


class ConfidenceTests(unittest.TestCase):
    def test_confidence_increases_with_more_checked_clauses(self):
        one_clause = assess_semantic_consistency([MATCHED_CLAUSE])
        two_clauses = assess_semantic_consistency([MATCHED_CLAUSE, MISMATCHED_CLAUSE])
        self.assertLess(one_clause.confidence, two_clauses.confidence)


class NonProseTableRowTests(unittest.TestCase):
    def test_minority_table_row_clause_is_excluded_from_a_prose_document_mean(self):
        # 1 prose + 1 non-prose = 50% structured, at (not over) the
        # structured-mode threshold, so this stays in prose mode -- the
        # single non-prose clause is excluded from the mean exactly as before.
        result = assess_semantic_consistency([MATCHED_CLAUSE, TABLE_ROW_CLAUSE])
        self.assertTrue(result.applicable)
        self.assertEqual(result.mode, "prose")
        self.assertEqual(len(result.checked), 1)
        self.assertEqual(result.checked[0].section_name, "Termination")
        self.assertTrue(any("non-prose" in e for e in result.evidence))

    def test_document_of_only_table_rows_uses_structured_mode_not_inapplicable(self):
        # Reworked 2026-07-20: a document that is ENTIRELY structured
        # field/table content used to be reported not-applicable outright
        # (no prose to compare). It now falls into structured mode and is
        # scored on field completeness instead -- this specific field has a
        # real, non-blank value ("ABCD1234EFGH" for "Engine Number"), so it
        # should score well, not just bail out.
        result = assess_semantic_consistency([TABLE_ROW_CLAUSE])
        self.assertTrue(result.applicable)
        self.assertEqual(result.mode, "structured")
        self.assertAlmostEqual(result.score, 1.0, places=4)
        self.assertTrue(any("Heading-body semantic similarity ignored" in e for e in result.evidence))


class StructuredDocumentModeTests(unittest.TestCase):
    # Regression coverage for the core bug this rework fixes: a highly
    # structured document (many field/table-style clauses, few or no prose
    # ones) must not be penalized by heading-body similarity, which is
    # near-zero for field/value content by construction, not because of tampering.
    STRUCTURED_CLAUSES = [
        {"section_name": "1. Policy Number", "text_content": "POL-88213-A"},
        {"section_name": "2. Sum Assured", "text_content": "Rs. 5,00,000"},
        {"section_name": "3. Premium", "text_content": "Rs. 12,000"},
        {"section_name": "4. Engine Number", "text_content": "EN1234567890"},
    ]

    def test_all_fields_populated_scores_high_in_structured_mode(self):
        result = assess_semantic_consistency(self.STRUCTURED_CLAUSES, document_type="Insurance Policy")
        self.assertTrue(result.applicable)
        self.assertEqual(result.mode, "structured")
        self.assertAlmostEqual(result.score, 1.0, places=4)
        self.assertTrue(any("Structured Insurance Policy detected" in e for e in result.evidence))

    def test_blank_field_value_lowers_structured_score(self):
        clauses_with_blank = self.STRUCTURED_CLAUSES + [{"section_name": "5. Nominee Name", "text_content": "N/A"}]
        result = assess_semantic_consistency(clauses_with_blank, document_type="Insurance Policy")
        self.assertLess(result.score, 1.0)

    def test_out_of_order_section_numbers_lower_structured_score(self):
        reordered = [
            {"section_name": "1. Policy Number", "text_content": "POL-88213-A"},
            {"section_name": "5. Sum Assured", "text_content": "Rs. 5,00,000"},
            {"section_name": "2. Premium", "text_content": "Rs. 12,000"},  # out of order
        ]
        in_order = [
            {"section_name": "1. Policy Number", "text_content": "POL-88213-A"},
            {"section_name": "2. Sum Assured", "text_content": "Rs. 5,00,000"},
            {"section_name": "3. Premium", "text_content": "Rs. 12,000"},
        ]
        reordered_result = assess_semantic_consistency(reordered)
        in_order_result = assess_semantic_consistency(in_order)
        self.assertLess(reordered_result.score, in_order_result.score)

    def test_structured_document_never_computes_heading_body_similarity(self):
        # The whole point: a structured document's score must not depend on
        # embedding similarity at all -- checked=[] proves the prose path
        # (which populates `checked`) never ran.
        result = assess_semantic_consistency(self.STRUCTURED_CLAUSES)
        self.assertEqual(result.checked, [])


if __name__ == "__main__":
    unittest.main()
