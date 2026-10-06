"""Layout regression checker for the paper (paper/main.pdf / paper/main.tex).

Catches two classes of layout bug a page-by-page visual pass can miss:

1. Overfull \\hbox warnings in a fresh compile log above a width threshold --
   text that LaTeX itself flagged as not fitting its line.
2. Geometric defects in the rendered PDF, via pdfplumber: words whose
   bounding box falls outside the page's left/right text margins, or whose
   bounding box overlaps another word's (the table-over-text collision this
   paper actually had on its padding table).

Usage:
    python scripts/check_layout.py                    # check the committed PDF (+ its log, if any)
    python scripts/check_layout.py --compile           # recompile fresh, then check both
    python scripts/check_layout.py --pdf X --log Y

Exit code 0 means zero failures; 1 means at least one failure was printed;
2 means the PDF/compile itself could not be produced.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEX = REPO_ROOT / "paper" / "main.tex"
DEFAULT_PDF = REPO_ROOT / "paper" / "main.pdf"
TECTONIC = REPO_ROOT / ".tools" / "tectonic.exe"

# Empirically measured from this document's own title page (page 1, US Letter
# 612x792pt, no known overflow there): words start no earlier than x=53.47 and
# end no later than x=559.72. A 1pt tolerance absorbs font-metric rounding;
# anything past that is a real margin violation, which is exactly how the
# known overflow bugs (TikZ labels, code identifiers, oversized tables) show
# up under pdfplumber.
PAGE_LEFT_MARGIN = 53.5
PAGE_RIGHT_MARGIN = 559.8
MARGIN_TOLERANCE_PT = 1.0
HBOX_THRESHOLD_PT = 1.0
# Minimum horizontal and vertical overlap (pt) to flag two words' boxes as a real collision.
# Adjacent lines of ordinary prose routinely show a 1-5pt *vertical* bbox overlap when one line
# has a descender/parenthesis or the other has inline math (XeTeX's math-italic glyphs report
# taller boxes than their visual ink) -- that is not a layout bug. A genuine float-over-text
# collision (e.g. a misplaced table row sitting on top of a text line) overlaps by much more than
# that, close to a full line height. OVERLAP_MIN_HY is set just above the largest such benign
# bleed measured on this document's own (now-clean) pages.
OVERLAP_MIN_HX = 1.0
OVERLAP_MIN_HY = 6.0

FILE_OPEN_RE = re.compile(r"\((?:\./)?(sections/[\w.]+|main\.tex)\b")
HBOX_RE = re.compile(
    r"Overfull \\hbox \((?P<amount>[\d.]+)pt too wide\) in paragraph at lines (?P<lines>[\d-]+)"
)


@dataclass
class Failure:
    kind: str
    page: object  # int or None
    location: str
    detail: str

    def render(self) -> str:
        page_str = f"page {self.page}" if self.page is not None else "(no page)"
        return f"  [{self.kind}] {page_str} {self.location}: {self.detail}"


def compile_fresh(tex_path: Path, outdir: Path) -> tuple[Path, Path]:
    """Compile tex_path with tectonic, keeping the log. Returns (pdf_path, log_path)."""
    outdir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            str(TECTONIC),
            str(tex_path),
            "--keep-logs",
            "--keep-intermediates",
            "--outdir",
            str(outdir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stem = tex_path.stem
    return outdir / f"{stem}.pdf", outdir / f"{stem}.log"


def check_hbox_log(log_path: Path, threshold_pt: float = HBOX_THRESHOLD_PT) -> list[Failure]:
    """Flag Overfull \\hbox warnings above threshold_pt, attributed to the .tex file open
    at that point in the log (best-effort: tracks the most recently opened section file,
    not a true nesting stack -- sufficient since floats/tables never open a new input file)."""
    if not log_path.exists():
        return []
    failures: list[Failure] = []
    current_file = "?"
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = FILE_OPEN_RE.search(line)
            if m:
                current_file = m.group(1)
            m = HBOX_RE.search(line)
            if m:
                amount = float(m.group("amount"))
                if amount > threshold_pt:
                    failures.append(
                        Failure(
                            kind="overfull_hbox",
                            page=None,
                            location=f"{current_file}:{m.group('lines')}",
                            detail=f"{amount:.2f}pt too wide",
                        )
                    )
    return failures


def check_margins_and_overlaps(pdf_path: Path) -> list[Failure]:
    import pdfplumber

    failures: list[Failure] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            words = page.extract_words()
            for w in words:
                if w["x0"] < PAGE_LEFT_MARGIN - MARGIN_TOLERANCE_PT:
                    failures.append(
                        Failure("margin_left", page_idx, f"x0={w['x0']:.1f}", w["text"])
                    )
                if w["x1"] > PAGE_RIGHT_MARGIN + MARGIN_TOLERANCE_PT:
                    failures.append(
                        Failure("margin_right", page_idx, f"x1={w['x1']:.1f}", w["text"])
                    )
            n = len(words)
            for i in range(n):
                a = words[i]
                for j in range(i + 1, n):
                    b = words[j]
                    if a["text"] == b["text"]:
                        # Same text at two spots is almost always a repeated table value
                        # (e.g. "0.011" in adjacent columns), not a real collision; skip it
                        # to avoid false positives from tight-but-correct table spacing.
                        continue
                    hx = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
                    hy = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
                    if hx > OVERLAP_MIN_HX and hy > OVERLAP_MIN_HY:
                        failures.append(
                            Failure(
                                "overlap",
                                page_idx,
                                f"({a['x0']:.1f},{a['top']:.1f}) vs ({b['x0']:.1f},{b['top']:.1f})",
                                f"{a['text']!r} overlaps {b['text']!r}",
                            )
                        )
    return failures


def check_quote_glyphs(pdf_path: Path) -> list[Failure]:
    """Catches the LaTeX \\`\\` typo (the grave-accent command, not two literal backtick
    characters) that produces a stray backtick/grave mark instead of a curly opening quote --
    found when the font this document builds with has no `` ligature. Two signals: a literal
    backtick or combining-grave character anywhere in the extracted text (neither has any
    legitimate use in this paper's body text), and more closing curly quotes (U+201D) than
    opening ones (U+201C) on a page, which happens when an opening quote silently vanishes."""
    import pdfplumber

    failures: list[Failure] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if "`" in text:
                failures.append(
                    Failure("stray_backtick", page_idx, "page text", "contains a backtick (`)")
                )
            if "̀" in text:
                failures.append(
                    Failure(
                        "stray_combining_grave",
                        page_idx,
                        "page text",
                        "contains a combining grave accent (U+0300)",
                    )
                )
            n_open = text.count("“")
            n_close = text.count("”")
            if n_close > n_open:
                failures.append(
                    Failure(
                        "unbalanced_quotes",
                        page_idx,
                        f"{n_close} closing vs {n_open} opening",
                        "more ” than “ on this page -- an opening quote likely "
                        "rendered as something else",
                    )
                )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tex", type=Path, default=DEFAULT_TEX)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument(
        "--compile",
        action="store_true",
        help="recompile --tex fresh into a temp dir (with --keep-logs) before checking",
    )
    parser.add_argument("--hbox-threshold", type=float, default=HBOX_THRESHOLD_PT)
    args = parser.parse_args(argv)

    pdf_path = args.pdf
    log_path = args.log

    if args.compile:
        tmp = Path(tempfile.mkdtemp(prefix="check_layout_"))
        try:
            pdf_path, log_path = compile_fresh(args.tex, tmp)
        except subprocess.CalledProcessError as e:
            print("error: tectonic failed to compile", args.tex, file=sys.stderr)
            print(e.stdout, file=sys.stderr)
            print(e.stderr, file=sys.stderr)
            return 2
    elif log_path is None:
        candidate = pdf_path.with_suffix(".log")
        log_path = candidate if candidate.exists() else None

    if not pdf_path.exists():
        print(f"error: PDF not found at {pdf_path}", file=sys.stderr)
        return 2

    failures: list[Failure] = []
    if log_path and log_path.exists():
        failures += check_hbox_log(log_path, args.hbox_threshold)
    else:
        print(f"note: no log file found; skipping overfull-hbox check", file=sys.stderr)

    failures += check_margins_and_overlaps(pdf_path)
    failures += check_quote_glyphs(pdf_path)

    if not failures:
        print(f"check_layout: 0 failures ({pdf_path})")
        return 0

    print(f"check_layout: {len(failures)} failures ({pdf_path})")
    for fail in failures:
        print(fail.render())
    return 1


if __name__ == "__main__":
    sys.exit(main())
