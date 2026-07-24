"""Tests for authenticity/digital.py (Factor 5 of the Authenticity
Verification Engine) — real QR-code and PDF-signature-field detection
round trips (no mocking of pyzbar/pikepdf), plus graceful non-applicability
for non-PDF sources and unreadable files.

Fixture PDFs are generated on the fly with qrcode+Pillow and pikepdf's
low-level object API rather than checked into the repo, so this test has
no binary test-data dependency.

Run with:  python -m unittest discover -s tests
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from authenticity.digital import assess_digital_verification


def _make_qr_pdf(path: Path, data: str = "AUTHENTICITY-TEST-12345") -> None:
    from PIL import Image
    import qrcode

    Image.init()  # PdfImagePlugin needs the JPEG codec registered before save("...pdf")
    img = qrcode.make(data).convert("RGB")
    img.save(str(path))


def _make_signature_field_pdf(path: Path) -> None:
    import pikepdf
    from pikepdf import Array, Dictionary, Name, String

    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(200, 200))
    sig_field = pdf.make_indirect(Dictionary(
        FT=Name("/Sig"), T=String("Signature1"), Rect=Array([0, 0, 100, 50]),
        Subtype=Name("/Widget"), F=4,
    ))
    pdf.Root.AcroForm = Dictionary(Fields=Array([sig_field]), SigFlags=3)
    page.Annots = Array([sig_field])
    pdf.save(str(path))


def _make_blank_pdf(path: Path) -> None:
    import pikepdf
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    pdf.save(str(path))


def _make_qr_and_signature_pdf(path: Path) -> None:
    """A single PDF carrying BOTH artifacts: generate the QR-only PDF first
    (Pillow/qrcode), then reopen it with pikepdf and add the same signature
    field _make_signature_field_pdf adds, in place."""
    import pikepdf
    from pikepdf import Array, Dictionary, Name, String

    _make_qr_pdf(path)
    with pikepdf.open(str(path), allow_overwriting_input=True) as pdf:
        page = pdf.pages[0]
        sig_field = pdf.make_indirect(Dictionary(
            FT=Name("/Sig"), T=String("Signature1"), Rect=Array([0, 0, 100, 50]),
            Subtype=Name("/Widget"), F=4,
        ))
        pdf.Root.AcroForm = Dictionary(Fields=Array([sig_field]), SigFlags=3)
        page.Annots = Array([sig_field])
        pdf.save(str(path))


class DigitalVerificationTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp(prefix="authenticity_digital_test_")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _path(self, name: str) -> Path:
        return Path(self._tmpdir) / name

    def test_qr_code_is_detected(self):
        # Reworked 2026-07-20: presence is bonus-only evidence on top of a
        # neutral 0.5 baseline (not a punishing 50/50 average) -- finding
        # one of the two artifacts now scores 0.75, clearly above neutral.
        path = self._path("qr.pdf")
        _make_qr_pdf(path)
        result = assess_digital_verification(str(path))
        self.assertTrue(result.applicable)
        self.assertTrue(result.has_qr_or_barcode)
        self.assertFalse(result.has_signature_field)
        self.assertEqual(result.score, 0.75)
        self.assertEqual(result.cryptographic_verification, "Unavailable")

    def test_signature_field_is_detected(self):
        path = self._path("sig.pdf")
        _make_signature_field_pdf(path)
        result = assess_digital_verification(str(path))
        self.assertTrue(result.applicable)
        self.assertFalse(result.has_qr_or_barcode)
        self.assertTrue(result.has_signature_field)
        self.assertEqual(result.score, 0.75)

    def test_both_artifacts_present_scores_full(self):
        path = self._path("both.pdf")
        _make_qr_and_signature_pdf(path)
        result = assess_digital_verification(str(path))
        self.assertTrue(result.has_qr_or_barcode)
        self.assertTrue(result.has_signature_field)
        self.assertEqual(result.score, 1.0)

    def test_blank_pdf_has_neither_and_is_neutral_not_penalized(self):
        # Reworked 2026-07-20: absence of both artifacts is the DEFAULT
        # state for the vast majority of real, genuine documents (almost no
        # document has a native PDF signature field) -- this must read as
        # neutral (0.5, "no evidence either way"), never as a 0.0 penalty.
        path = self._path("blank.pdf")
        _make_blank_pdf(path)
        result = assess_digital_verification(str(path))
        self.assertTrue(result.applicable)
        self.assertFalse(result.has_qr_or_barcode)
        self.assertFalse(result.has_signature_field)
        self.assertEqual(result.score, 0.5)
        self.assertGreater(result.pages_scanned_for_qr, 0)
        self.assertTrue(any("no penalty" in e for e in result.evidence))
        self.assertTrue(any("Cryptographic verification unavailable" in e for e in result.evidence))

    def test_non_pdf_extension_is_not_applicable(self):
        path = self._path("document.docx")
        path.write_text("not really a docx, extension is all that matters here")
        result = assess_digital_verification(str(path))
        self.assertFalse(result.applicable)

    def test_missing_file_is_not_applicable(self):
        result = assess_digital_verification(str(self._path("does_not_exist.pdf")))
        self.assertFalse(result.applicable)

    def test_none_file_path_is_not_applicable(self):
        result = assess_digital_verification(None)
        self.assertFalse(result.applicable)


if __name__ == "__main__":
    unittest.main()
