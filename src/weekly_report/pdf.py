"""Prints the report HTML to PDF with headless Chrome, then checks the PDF is not blank."""

import os
import re
import subprocess
import tempfile
from pathlib import Path

CHROME_SUFFIX = Path("Google/Chrome/Application/chrome.exe")
STANDARD_PATHS = [
    Path(os.environ.get(variable, default)) / CHROME_SUFFIX
    for variable, default in [
        ("ProgramFiles", "C:/Program Files"),
        ("ProgramFiles(x86)", "C:/Program Files (x86)"),
        ("LOCALAPPDATA", str(Path.home() / "AppData/Local")),
    ]
]
PAGE = re.compile(rb"/Type\s*/Page\b")
TIMEOUT_SECONDS = 120


class PdfError(Exception):
    pass


def find_chrome(override: Path | None, candidates: list[Path] = STANDARD_PATHS) -> Path:
    if override is not None:
        if override.is_file():
            return override
        raise PdfError(f"no Chrome at {override}, the chrome path in report.toml")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise PdfError("Chrome not found; set chrome in config/report.toml to its path")


def chrome_command(chrome: Path, html: Path, pdf: Path, profile: Path) -> list[str]:
    return [
        str(chrome),
        "--headless",
        "--disable-gpu",
        f"--user-data-dir={profile}",
        "--window-size=794,1123",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf}",
        html.resolve().as_uri(),
    ]


def check_pdf(data: bytes, min_pages: int) -> int:
    """The PDF's page count; fails when it is short of `min_pages` or holds no text."""
    if not data.startswith(b"%PDF"):
        raise PdfError("Chrome's output is not a PDF")
    pages = len(PAGE.findall(data))
    if pages < min_pages:
        raise PdfError(f"the PDF has {pages} page(s), expected at least {min_pages}")
    if b"/Font" not in data:
        raise PdfError("the PDF is blank: it holds no text")
    return pages


def print_pdf(chrome: Path, html: Path, pdf: Path, min_pages: int) -> int:
    """Prints `html` to `pdf` and returns its page count."""
    pdf.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        command = chrome_command(chrome, html, pdf.resolve(), Path(profile))
        try:
            subprocess.run(
                command, check=True, capture_output=True, timeout=TIMEOUT_SECONDS
            )
        except (subprocess.SubprocessError, OSError) as error:
            raise PdfError(f"Chrome failed to print: {error}") from error
    if not pdf.is_file():
        raise PdfError("Chrome wrote no PDF")
    return check_pdf(pdf.read_bytes(), min_pages)
