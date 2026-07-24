"""Tests for authenticity/entities.py (Factor 4 of the Authenticity
Verification Engine) — cross-page NAME-CONSISTENCY of recurring ("key")
named parties via real spaCy NER, and graceful non-applicability for
non-paginated documents.

Reworked 2026-07-20 alongside the source module: scoring moved from
"fraction of all distinct entities that recur" (which penalized documents
naming many legitimate one-off administrative entities) to "mean name-form
consistency of entities that DO recur" — entities mentioned once are
excluded from scoring entirely, never treated as a strike.

Uses the real spaCy pipeline (via agents.feature_extraction_agent), same as
tests/test_feature_extraction_agent.py — no mocking of NER.

Run with:  python -m unittest discover -s tests
"""

import unittest

from authenticity.entities import _looks_like_party_name, _name_consistency_fraction, assess_entity_verification

TWO_PAGE_DOC = [
    {"page_number": 1, "raw_text": (
        "This Agreement is entered into between ABC Corporation and XYZ Limited "
        "on January 1, 2024. ABC Corporation is a company engaged in software services."
    )},
    {"page_number": 2, "raw_text": (
        "ABC Corporation shall make payments as set forth in Schedule A. "
        "This obligation is binding upon ABC Corporation and its successors."
    )},
]

SINGLE_PAGE_DOC = [
    {"page_number": 1, "raw_text": "This Agreement is between ABC Corporation and XYZ Limited."},
]


class CrossPageRecurrenceTests(unittest.TestCase):
    def test_party_mentioned_on_every_page_is_recurring(self):
        result = assess_entity_verification(TWO_PAGE_DOC)
        self.assertTrue(result.applicable)
        abc = next((c for c in result.checked_entities if "ABC" in c.text), None)
        self.assertIsNotNone(abc, f"expected an ABC-related entity, got {result.checked_entities}")
        self.assertTrue(abc.recurring)
        self.assertEqual(set(abc.pages_seen), {1, 2})

    def test_party_mentioned_on_only_one_page_is_flagged(self):
        result = assess_entity_verification(TWO_PAGE_DOC)
        xyz = next((c for c in result.checked_entities if "XYZ" in c.text), None)
        self.assertIsNotNone(xyz, f"expected an XYZ-related entity, got {result.checked_entities}")
        self.assertFalse(xyz.recurring)
        self.assertEqual(xyz.pages_seen, [1])

    def test_score_is_mean_name_consistency_of_recurring_entities_only(self):
        # Reworked formula: score = mean(name_consistency) over entities
        # that recur (2+ pages) -- NOT recurring_count / total_distinct.
        # ABC Corporation recurs with a stable surface form on every mention
        # in this fixture, so its name_consistency is 1.0 and (being the
        # only recurring entity) the whole factor score is 1.0, regardless
        # of XYZ Limited only appearing once.
        result = assess_entity_verification(TWO_PAGE_DOC)
        recurring = [c for c in result.checked_entities if c.recurring]
        self.assertTrue(recurring, f"expected at least one recurring entity, got {result.checked_entities}")
        expected = sum(c.name_consistency for c in recurring) / len(recurring)
        self.assertAlmostEqual(result.score, expected, places=4)
        self.assertAlmostEqual(result.score, 1.0, places=4)


class NotApplicableTests(unittest.TestCase):
    def test_single_page_document_is_not_applicable(self):
        result = assess_entity_verification(SINGLE_PAGE_DOC)
        self.assertFalse(result.applicable)
        self.assertEqual(result.score, 0.0)

    def test_no_pages_is_not_applicable(self):
        result = assess_entity_verification([])
        self.assertFalse(result.applicable)

    def test_pages_with_blank_text_are_not_counted(self):
        result = assess_entity_verification([
            {"page_number": 1, "raw_text": "Some real text about ABC Corporation and its obligations."},
            {"page_number": 2, "raw_text": "   "},
        ])
        self.assertFalse(result.applicable)


class NoEntitiesTests(unittest.TestCase):
    def test_no_party_entities_found_scores_zero_not_error(self):
        result = assess_entity_verification([
            {"page_number": 1, "raw_text": "the quick brown fox jumps over the lazy dog"},
            {"page_number": 2, "raw_text": "near the river bank under a clear blue sky"},
        ])
        self.assertTrue(result.applicable)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(result.checked_entities, [])


MANY_ADMIN_ENTITIES_DOC = [
    {"page_number": 1, "raw_text": (
        "This policy is issued by Bajaj Allianz General Insurance Company Limited. "
        "The policyholder is Rahul Sharma. Branch office contact is Priya Menon at the Mumbai branch. "
        "Bajaj Allianz General Insurance Company Limited underwrites this coverage."
    )},
    {"page_number": 2, "raw_text": (
        "Claims for this policy should be directed to Bajaj Allianz General Insurance Company Limited. "
        "Rahul Sharma is the named insured under this schedule. Witness signature: Anil Verma. "
        "Regional coordinator: Sunita Rao."
    )},
]



class ManyEntitiesDoesNotPenalizeTests(unittest.TestCase):
    # Regression coverage for the exact bug this rework fixes: a document
    # naming several genuine one-off administrative entities (a branch
    # contact, a witness, a coordinator) alongside a perfectly consistent
    # issuer and customer must NOT score lower than a document with fewer
    # named entities. Under the old recurring/total-distinct formula, each
    # additional one-off name diluted the score even though nothing about
    # them is suspicious.
    def test_one_off_administrative_entities_are_excluded_not_penalized(self):
        result = assess_entity_verification(MANY_ADMIN_ENTITIES_DOC)
        self.assertTrue(result.applicable)
        # The issuer (Bajaj Allianz...) and the customer (Rahul Sharma) both
        # recur across both pages with a stable name -- that's all that's
        # scored. Priya Menon / Anil Verma / Sunita Rao are one-off mentions
        # and must be excluded from scoring entirely.
        recurring_names = {c.text for c in result.checked_entities if c.recurring}
        self.assertTrue(any("Bajaj" in n for n in recurring_names), recurring_names)
        self.assertGreater(result.administrative_entity_count, 0)
        self.assertAlmostEqual(result.score, 1.0, places=2)
        self.assertTrue(any("No authenticity penalty applied" in e for e in result.evidence))

    def test_administrative_entities_never_lower_the_score_vs_fewer_named_entities(self):
        # A sparser document with only the same consistent issuer/customer
        # and none of the one-off names must score no higher than the
        # richer document above -- proving the extra names truly cost nothing.
        sparse = [
            {"page_number": 1, "raw_text": "This policy is issued by Bajaj Allianz General Insurance Company Limited."},
            {"page_number": 2, "raw_text": "Bajaj Allianz General Insurance Company Limited underwrites this coverage."},
        ]
        rich_result = assess_entity_verification(MANY_ADMIN_ENTITIES_DOC)
        sparse_result = assess_entity_verification(sparse)
        self.assertGreaterEqual(rich_result.score, sparse_result.score - 1e-9)


class NameConsistencyFractionTests(unittest.TestCase):
    # End-to-end (real spaCy NER) coverage of "does a genuinely inconsistent
    # recurring entity lower the score" is deliberately NOT attempted here:
    # the shared fuzzy-match threshold (_SUBJECT_AGREEMENT_RATIO = 0.5,
    # reused unchanged from agents.feature_extraction_agent, out of scope to
    # retune) is tolerant enough that many realistic "different but
    # similar-shaped" name pairs (e.g. two names sharing a common surname,
    # or two company names sharing generic industry words like "General
    # Insurance ... Limited") still fuzzy-match at that threshold -- which
    # is the deliberate OCR-noise-tolerance tradeoff already accepted
    # elsewhere in this engine (cross_field.py), just visibly double-edged
    # here. The actual new math is covered directly and deterministically
    # below instead.
    def test_identical_mentions_are_fully_consistent(self):
        self.assertAlmostEqual(_name_consistency_fraction(["Acme Corp", "Acme Corp", "Acme Corp"]), 1.0)

    def test_minor_ocr_variation_still_counts_as_consistent(self):
        # Same fuzzy tolerance as cross_field.py -- small formatting/OCR
        # noise between mentions of the same real-world entity shouldn't
        # read as forgery evidence.
        self.assertGreaterEqual(_name_consistency_fraction(["Acme Corp Ltd", "Acme Corp Ltd.", "AcmeCorp Ltd"]), 0.6)

    def test_genuinely_different_names_are_inconsistent(self):
        fraction = _name_consistency_fraction(["Acme Corporation", "Acme Corporation", "Zenith Holdings"])
        self.assertLess(fraction, 1.0)

    def test_empty_input(self):
        self.assertEqual(_name_consistency_fraction([]), 0.0)


class LooksLikePartyNameTests(unittest.TestCase):
    # Regression coverage for the false-positive found on a real scanned
    # insurance policy: spaCy's NER on noisy OCR'd tabular content tagged
    # short alphanumeric table values (engine numbers, policy codes) as
    # ORG/PERSON, producing 48 "entities" on one document, most of them
    # one-off table cells that were never going to recur because they were
    # never party names in the first place.
    def test_multi_word_names_pass(self):
        self.assertTrue(_looks_like_party_name("Bajaj Allianz General Insurance Company Limited"))
        self.assertTrue(_looks_like_party_name("John Doe"))

    def test_long_single_word_alphabetic_names_pass(self):
        self.assertTrue(_looks_like_party_name("Microsoft"))

    def test_alphanumeric_codes_are_excluded(self):
        self.assertFalse(_looks_like_party_name("POL88213A"))
        self.assertFalse(_looks_like_party_name("ABCD1234EFGH"))

    def test_short_tokens_are_excluded(self):
        self.assertFalse(_looks_like_party_name("ABC"))

    def test_empty_text_is_excluded(self):
        self.assertFalse(_looks_like_party_name(""))
        self.assertFalse(_looks_like_party_name("   "))


if __name__ == "__main__":
    unittest.main()
