import tempfile
import unittest
from pathlib import Path

from weekly_report.pdf import PdfError, check_pdf, chrome_command, find_chrome

PAGE = b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> >>"


def pdf_bytes(pages: int, page: bytes = PAGE) -> bytes:
    objects = [b"%PDF-1.4", b"<< /Type /Pages /Count %d >>" % pages]
    objects += [page] * pages
    return b"\n".join(objects)


class FindChromeTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.installed = self.root / "installed" / "chrome.exe"
        self.installed.parent.mkdir()
        self.installed.write_bytes(b"")
        self.missing = self.root / "missing" / "chrome.exe"

    def test_the_first_installed_standard_path_wins(self):
        self.assertEqual(
            find_chrome(None, [self.missing, self.installed]), self.installed
        )

    def test_an_override_wins_over_standard_paths(self):
        override = self.root / "chrome.exe"
        override.write_bytes(b"")
        self.assertEqual(find_chrome(override, [self.installed]), override)

    def test_a_missing_override_is_named_and_not_skipped(self):
        with self.assertRaises(PdfError) as raised:
            find_chrome(self.missing, [self.installed])
        self.assertIn(str(self.missing), str(raised.exception))

    def test_no_chrome_anywhere_points_at_the_override(self):
        with self.assertRaises(PdfError) as raised:
            find_chrome(None, [self.missing])
        self.assertIn("report.toml", str(raised.exception))


class ChromeCommandTest(unittest.TestCase):
    def test_prints_a4_without_headers_in_its_own_profile(self):
        root = Path(tempfile.gettempdir()).resolve()
        html = root / "out" / "report.html"
        command = chrome_command(
            Path("chrome.exe"), html, root / "out" / "report.pdf", root / "profile"
        )
        self.assertEqual(
            command,
            [
                "chrome.exe",
                "--headless",
                "--disable-gpu",
                f"--user-data-dir={root / 'profile'}",
                "--window-size=794,1123",
                "--no-pdf-header-footer",
                f"--print-to-pdf={root / 'out' / 'report.pdf'}",
                html.as_uri(),
            ],
        )


class CheckPdfTest(unittest.TestCase):
    def test_counts_pages(self):
        self.assertEqual(check_pdf(pdf_bytes(3), min_pages=1), 3)

    def test_fewer_pages_than_expected_fails(self):
        with self.assertRaises(PdfError) as raised:
            check_pdf(pdf_bytes(1), min_pages=2)
        self.assertIn("1 page", str(raised.exception))

    def test_a_page_with_no_text_is_blank(self):
        with self.assertRaises(PdfError) as raised:
            check_pdf(pdf_bytes(1, b"<< /Type /Page /Parent 2 0 R >>"), min_pages=1)
        self.assertIn("blank", str(raised.exception))

    def test_not_a_pdf_fails(self):
        with self.assertRaises(PdfError):
            check_pdf(b"", min_pages=1)


if __name__ == "__main__":
    unittest.main()
