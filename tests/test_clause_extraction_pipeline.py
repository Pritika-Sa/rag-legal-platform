import unittest

from agents.clause_identifier_agent import (
    IdentifiedClause,
    _deduplicate_clauses,
    _segment_into_clause_candidates,
    identify_clauses,
)
from agents.parser_agent import (
    _extract_page_tables,
    _is_section_heading,
    _reconstruct_text_from_words,
    _strip_cid_garbage,
    _table_row_to_text,
)


class SegmentationTests(unittest.TestCase):
    def test_splits_on_numbered_markers(self):
        text = (
            "Conditions of Coverage\n"
            "1. Own Damage cover includes accidental damage to the insured vehicle.\n"
            "2. Third Party Liability cover includes bodily injury and property damage.\n"
            "3. Personal Accident cover includes death and disability benefits."
        )
        candidates = _segment_into_clause_candidates(text)
        self.assertGreaterEqual(len(candidates), 3)
        self.assertTrue(any(c.startswith("1.") for c in candidates))
        self.assertTrue(any(c.startswith("2.") for c in candidates))
        self.assertTrue(any(c.startswith("3.") for c in candidates))

    def test_splits_on_lettered_markers(self):
        text = (
            "Exclusions\n"
            "a) Loss due to war or nuclear risk is excluded.\n"
            "b) Loss due to normal wear and tear is excluded.\n"
            "c) Loss while driving under the influence of alcohol is excluded."
        )
        candidates = _segment_into_clause_candidates(text)
        self.assertGreaterEqual(len(candidates), 3)

    def test_splits_on_bullet_markers(self):
        text = (
            "Notices\n"
            "- All notices shall be in writing and sent to the registered address.\n"
            "- Notice by email shall be deemed effective upon transmission.\n"
            "- Notice by post shall be deemed effective five days after posting."
        )
        candidates = _segment_into_clause_candidates(text)
        self.assertGreaterEqual(len(candidates), 3)

    def test_splits_on_embedded_subheading(self):
        text = (
            "General Provisions\n"
            "This policy is subject to the terms set out below and forms part of the contract.\n"
            "Cancellation Conditions\n"
            "The Company may cancel this policy by giving fifteen days written notice to the insured.\n"
        )
        candidates = _segment_into_clause_candidates(text)
        self.assertTrue(any("Cancellation Conditions" in c for c in candidates))
        # the embedded heading must start its own candidate, not stay fused
        # into the first paragraph
        self.assertFalse(any("terms set out below" in c and "Cancellation Conditions" in c for c in candidates))

    def test_old_behavior_still_works_for_blank_line_paragraphs(self):
        text = "First provision about payment terms.\n\nSecond provision about termination rights."
        candidates = _segment_into_clause_candidates(text)
        self.assertEqual(len(candidates), 2)


class TableExtractionTests(unittest.TestCase):
    def test_table_row_to_text_with_header(self):
        header = ["Coverage Type", "Sum Insured", "Premium"]
        row = ["Own Damage", "500000", "12000"]
        text = _table_row_to_text(header, row)
        self.assertIn("Coverage Type: Own Damage", text)
        self.assertIn("Sum Insured: 500000", text)
        self.assertIn("Premium: 12000", text)

    def test_table_row_to_text_without_header_falls_back_to_cell_join(self):
        text = _table_row_to_text([], ["Own Damage", "500000"])
        self.assertIn("Own Damage", text)
        self.assertIn("500000", text)

    def test_table_row_to_text_strips_cid_garbage(self):
        header = ["(cid:4)(cid:5)Coverage"]
        row = ["Own Damage"]
        text = _table_row_to_text(header, row)
        self.assertNotIn("cid:", text)
        self.assertIn("Coverage", text)
        self.assertIn("Own Damage", text)

    def test_extract_page_tables_converts_each_row_to_own_section(self):
        class _FakeTable:
            bbox = (0, 0, 100, 100)

            def extract(self, x_tolerance=3):
                return [
                    ["Registration Number", "Engine Number"],
                    ["TN36AC8885", "E3N8E0073051"],
                    ["TN01AB1234", "E9N9E0000001"],
                ]

        class _FakePage:
            def find_tables(self):
                return [_FakeTable()]

        sections, bboxes = _extract_page_tables(_FakePage(), page_num=6)
        self.assertEqual(len(sections), 2)
        self.assertEqual(len(bboxes), 1)
        self.assertIn("Registration Number: TN36AC8885", sections[0]["text_content"])
        self.assertEqual(sections[0]["page_num"], 6)


class WordGlyphReconstructionTests(unittest.TestCase):
    def test_reconstructs_spaces_between_glued_words(self):
        words = [
            {"text": "Registered", "top": 10.0, "x0": 0},
            {"text": "and", "top": 10.2, "x0": 50},
            {"text": "Head", "top": 10.1, "x0": 70},
            {"text": "Office:", "top": 10.0, "x0": 100},
            {"text": "Coverage", "top": 40.0, "x0": 0},
            {"text": "Details", "top": 40.1, "x0": 60},
        ]
        text = _reconstruct_text_from_words(words)
        self.assertEqual(text, "Registered and Head Office:\nCoverage Details")

    def test_strip_cid_garbage(self):
        self.assertEqual(_strip_cid_garbage("(cid:4)(cid:5)BAJAJ ALLIANZ"), "BAJAJ ALLIANZ")
        self.assertEqual(_strip_cid_garbage("No garbage here"), "No garbage here")

    def test_empty_words_returns_empty_string(self):
        self.assertEqual(_reconstruct_text_from_words([]), "")


class HeadingDetectionTests(unittest.TestCase):
    def test_recognizes_title_case_headings_with_connector_words(self):
        for heading in ["Conditions of Coverage", "Notice of Cancellation", "Limitation of Use", "Proof of Loss"]:
            with self.subTest(heading=heading):
                self.assertTrue(_is_section_heading(heading))

    def test_still_recognizes_original_patterns(self):
        for heading in ["Section 3.2 Termination", "TERMINATION", "Governing Law", "III. Payment"]:
            with self.subTest(heading=heading):
                self.assertTrue(_is_section_heading(heading))

    def test_does_not_misfire_on_ordinary_sentences(self):
        sentence = "The company shall pay the amount due within thirty days of receipt of invoice."
        self.assertFalse(_is_section_heading(sentence))


class DeduplicationTests(unittest.TestCase):
    def _clause(self, text, confidence=0.5, clause_type="Compliance"):
        return IdentifiedClause(
            clause_type=clause_type,
            clause_title="Title",
            clause_text=text,
            confidence_score=confidence,
            page_number=1,
            start_position=0,
            end_position=len(text),
        )

    def test_near_duplicate_clauses_collapse_to_one(self):
        a = self._clause("I hereby declare that all information provided above is true and correct.", 0.4)
        b = self._clause("I hereby declare that all information provided above is true and correct!", 0.6)
        result = _deduplicate_clauses([a, b])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].confidence_score, 0.6)

    def test_distinct_clauses_are_both_kept(self):
        a = self._clause("The premium is payable annually in advance.", 0.5)
        b = self._clause("The policy may be cancelled by either party on notice.", 0.5)
        result = _deduplicate_clauses([a, b])
        self.assertEqual(len(result), 2)

    def test_boilerplate_differing_only_in_a_number_is_not_deduped(self):
        """Regression test: two clauses that are >90% textually similar but
        disagree on the one number that matters (a penalty percentage) must
        both survive -- this is exactly the case contradiction_agent's own
        duplicate/conflict detection exists to catch, and text-similarity-only
        dedup was silently discarding one of the two distinct financial terms."""
        a = self._clause(
            "CLAUSE SIX - DEFAULT: Payment delay will result in a penalty of 8% on the installment, "
            "late interest of 1% per month, and possible execution of the guarantee.",
            confidence=0.45,
        )
        b = self._clause(
            "CLAUSE SIX - DEFAULT: Payment delay will result in a penalty of 2% on the installment, "
            "late interest of 1% per month, and possible execution of the guarantee.",
            confidence=0.45,
        )
        # sanity check: these really are near-duplicate text (the bug's precondition)
        from difflib import SequenceMatcher
        self.assertGreaterEqual(SequenceMatcher(None, a.clause_text.lower(), b.clause_text.lower()).ratio(), 0.90)

        result = _deduplicate_clauses([a, b])
        self.assertEqual(len(result), 2)
        texts = {c.clause_text for c in result}
        self.assertIn(a.clause_text, texts)
        self.assertIn(b.clause_text, texts)


class EndToEndSegmentationYieldTests(unittest.TestCase):
    """Guards against the original bug: a document with many distinct
    provisions bundled under a few headings must yield many identified
    clauses, not 2-3 oversized ones."""

    def test_synthetic_insurance_like_document_yields_multiple_clauses(self):
        full_text = (
            "Coverage and Scope\n"
            "1. This policy provides coverage for own damage losses up to the policy limits stated in the schedule.\n"
            "2. This policy provides coverage for third-party liability arising from an insured event.\n\n"
            "Premium\n"
            "The annual premium payable is Rs. 12,340, due before the policy's grace period expires.\n\n"
            "Deductible and Exclusions\n"
            "Claims are subject to a compulsory deductible, and losses arising from war are excluded under the policy exclusions.\n\n"
            "Cancellation\n"
            "The Company may cancel this policy by giving fifteen days' written notice to the insured.\n\n"
            "Claims Procedure\n"
            "The insured shall file a claim and submit proof of loss within thirty days of the covered event.\n"
        )
        page_mapping = [{"page_number": 1, "text_content": full_text}]
        clauses = identify_clauses(full_text, page_mapping)
        self.assertGreaterEqual(len(clauses), 5)
        detected_types = {c.clause_type for c in clauses}
        self.assertIn("Coverage and Scope", detected_types)
        self.assertIn("Premium", detected_types)
        self.assertIn("Cancellation", detected_types)


if __name__ == "__main__":
    unittest.main()
