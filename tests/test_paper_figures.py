"""Paper figures must not silently drift from the data they're built from.

F5's caption states A1's realized mimicry distance as a literal number (DECISIONS.md s23: "A1"
is the jitter-0.70 run, realized NN ~0.56 -- not copy fidelity, which is the point of the RF TPR
channel). A LaTeX caption is a string an editor can hand-edit without re-running anything, so
nothing enforces that it still matches the CSV after a re-run. This test does.
"""

import re
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from experiments.paper_figures import _mechanism_rows  # noqa: E402

CAPTION_FILE = Path("paper/sections/06_attack.tex")


def _skip_if_no_data():
    if not Path("results/phase0/export/summary.csv").exists():
        pytest.skip("results/phase0/export/summary.csv not present")


def test_a1_realized_nn_matches_decisions_s23():
    _skip_if_no_data()
    t = _mechanism_rows()
    a1_nn = t.loc[t.scenario == "a1", "fidelity_median"].iloc[0]
    # DECISIONS.md s23 states "realized NN ~0.56" for the jitter-0.70 mechanism run; this is
    # NOT copy fidelity (the FPR channel's regime, s23: realized NN <~ 0.011-0.014). If this
    # ever fails, the mechanism run changed and s23 / the F5 caption need updating together.
    assert a1_nn == pytest.approx(0.56, abs=0.01)
    assert a1_nn > 0.05, "this must stay far from copy fidelity, or the F5 caption is wrong"


def test_f5_caption_states_the_same_distance_as_the_csv():
    _skip_if_no_data()
    t = _mechanism_rows()
    a1_nn = t.loc[t.scenario == "a1", "fidelity_median"].iloc[0]
    caption = CAPTION_FILE.read_text(encoding="utf-8")
    m = re.search(r"realized NN \$\\approx(\d+\.\d+)\$", caption)
    assert m, f"expected a 'realized NN $\\approx0.NN$' figure in {CAPTION_FILE}'s F5 caption"
    assert float(m.group(1)) == pytest.approx(a1_nn, abs=0.01)


def test_f5_caption_does_not_call_a1_copy_fidelity():
    caption = CAPTION_FILE.read_text(encoding="utf-8")
    start = caption.index("fig:f5-mechanism")
    f5_block = caption[max(0, start - 1500):start]
    assert "copy fidelity" not in f5_block.lower() or "not copy fidelity" in f5_block.lower()
