"""Tests for authenticity/metadata.py (Factor 6 of the Authenticity
Verification Engine) — real PDF/DOCX metadata date-order validation (no
mocking of extract_pdf_metadata/extract_docx_metadata), and graceful
non-applicability for unsupported formats and missing/error metadata.

Fixture files are generated on the fly with pikepdf and python-docx.

Run with:  python -m unittest discover -s tests
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from authenticity.metadata import assess_metadata_validation


def _make_pdf(path: Path, creation_date: str = None, mod_date: str = None, populate_extra: bool = True) -> None:
    import pikepdf
    from pikepdf import String

    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    if creation_date:
        pdf.docinfo["/CreationDate"] = String(creation_date)
    if mod_date:
        pdf.docinfo["/ModDate"] = String(mod_date)
    if populate_extra:
        pdf.docinfo["/Author"] = String("Test Author")
        pdf.docinfo["/Producer"] = String("Test Producer")
    pdf.save(str(path))


def _make_docx(path: Path, created=None, modified=None) -> None:
    import docx
    doc = docx.Document()
    doc.add_paragraph("Some agreement text.")
    if created:
        doc.core_properties.created = created
    if modified:
        doc.core_properties.modified = modified
    doc.core_properties.author = "Test Author"
    doc.save(str(path))


class PdfDateConsistencyTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="authenticity_metadata_test_")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _path(self, name: str) -> Path:
        return Path(self._tmpdir) / name

    def test_modified_after_created_is_consistent(self):
        path = self._path("good.pdf")
        _make_pdf(path, "D:20200101120000+00'00'", "D:20240115093000+00'00'")
        result = assess_metadata_validation(str(path))
        self.assertTrue(result.applicable)
        self.assertEqual(result.score, 1.0)
        self.assertGreater(result.confidence, 0.0)

    def test_modified_before_created_is_inconsistent(self):
        path = self._path("tampered.pdf")
        _make_pdf(path, "D:20240115093000+00'00'", "D:20200101120000+00'00'")
        result = assess_metadata_validation(str(path))
        self.assertTrue(result.applicable)
        self.assertEqual(result.score, 0.0)
        self.assertTrue(any("INCONSISTENT" in e for e in result.evidence))

    def test_missing_dates_is_vacuous_pass_with_zero_confidence(self):
        path = self._path("no_dates.pdf")
        _make_pdf(path, creation_date=None, mod_date=None)
        result = assess_metadata_validation(str(path))
        self.assertTrue(result.applicable)
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.confidence, 0.0)

    def test_more_populated_fields_increase_confidence(self):
        sparse_path = self._path("sparse.pdf")
        _make_pdf(sparse_path, "D:20200101120000+00'00'", "D:20240115093000+00'00'", populate_extra=False)
        rich_path = self._path("rich.pdf")
        _make_pdf(rich_path, "D:20200101120000+00'00'", "D:20240115093000+00'00'", populate_extra=True)

        sparse_result = assess_metadata_validation(str(sparse_path))
        rich_result = assess_metadata_validation(str(rich_path))
        self.assertLess(sparse_result.confidence, rich_result.confidence)


class DocxDateConsistencyTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="authenticity_metadata_docx_test_")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _path(self, name: str) -> Path:
        return Path(self._tmpdir) / name

    def test_docx_modified_after_created_is_consistent(self):
        from datetime import datetime
        path = self._path("good.docx")
        _make_docx(path, created=datetime(2020, 1, 1, 12, 0, 0), modified=datetime(2024, 1, 15, 9, 30, 0))
        result = assess_metadata_validation(str(path))
        self.assertTrue(result.applicable)
        self.assertEqual(result.score, 1.0)

    def test_docx_modified_before_created_is_inconsistent(self):
        from datetime import datetime
        path = self._path("tampered.docx")
        _make_docx(path, created=datetime(2024, 1, 15, 9, 30, 0), modified=datetime(2020, 1, 1, 12, 0, 0))
        result = assess_metadata_validation(str(path))
        self.assertTrue(result.applicable)
        self.assertEqual(result.score, 0.0)


class NotApplicableTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="authenticity_metadata_na_test_")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _path(self, name: str) -> Path:
        return Path(self._tmpdir) / name

    def test_txt_source_is_not_applicable(self):
        path = self._path("doc.txt")
        path.write_text("plain text document")
        result = assess_metadata_validation(str(path))
        self.assertFalse(result.applicable)

    def test_missing_file_is_not_applicable(self):
        result = assess_metadata_validation(str(self._path("nope.pdf")))
        self.assertFalse(result.applicable)

    def test_none_path_is_not_applicable(self):
        result = assess_metadata_validation(None)
        self.assertFalse(result.applicable)

    def test_corrupted_pdf_metadata_extraction_failure_is_not_applicable(self):
        path = self._path("corrupt.pdf")
        path.write_text("this is not a real pdf file")
        result = assess_metadata_validation(str(path))
        self.assertFalse(result.applicable)


if __name__ == "__main__":
    unittest.main()
