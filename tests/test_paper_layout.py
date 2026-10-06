"""The compiled paper must not regress on margin overflows or table-over-text collisions.

scripts/check_layout.py is the actual checker (pdfplumber-based geometry checks, plus an
Overfull-\\hbox log check when a log is available). This test runs it against the committed
paper/main.pdf -- the artifact a reader actually opens -- so a layout regression is caught by
`pytest`, not just by a page-by-page visual pass.
"""

from pathlib import Path

import pytest

pytest.importorskip("pdfplumber")

from scripts.check_layout import check_margins_and_overlaps, check_quote_glyphs  # noqa: E402

PDF_PATH = Path("paper/main.pdf")


def test_committed_pdf_has_no_margin_or_overlap_failures():
    if not PDF_PATH.exists():
        pytest.skip(f"{PDF_PATH} not present")
    failures = check_margins_and_overlaps(PDF_PATH)
    assert not failures, "\n".join(f.render() for f in failures)


def test_committed_pdf_has_no_broken_quote_glyphs():
    """Regression test for the \\`\\` typo (LaTeX's grave-accent command, not the double-backtick
    quote-opening convention) that this document's font rendered as a stray backtick/combining
    grave accent instead of a curly opening quote."""
    if not PDF_PATH.exists():
        pytest.skip(f"{PDF_PATH} not present")
    failures = check_quote_glyphs(PDF_PATH)
    assert not failures, "\n".join(f.render() for f in failures)
