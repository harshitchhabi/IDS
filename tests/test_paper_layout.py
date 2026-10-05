"""The compiled paper must not regress on margin overflows or table-over-text collisions.

scripts/check_layout.py is the actual checker (pdfplumber-based geometry checks, plus an
Overfull-\\hbox log check when a log is available). This test runs it against the committed
paper/main.pdf -- the artifact a reader actually opens -- so a layout regression is caught by
`pytest`, not just by a page-by-page visual pass.
"""

from pathlib import Path

import pytest

pytest.importorskip("pdfplumber")

from scripts.check_layout import check_margins_and_overlaps  # noqa: E402

PDF_PATH = Path("paper/main.pdf")


def test_committed_pdf_has_no_margin_or_overlap_failures():
    if not PDF_PATH.exists():
        pytest.skip(f"{PDF_PATH} not present")
    failures = check_margins_and_overlaps(PDF_PATH)
    assert not failures, "\n".join(f.render() for f in failures)
