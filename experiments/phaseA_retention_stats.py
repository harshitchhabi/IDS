"""Phase A item C (DECISIONS.md s29.C): A1's fixed-threshold FPR damage under three retention
policies -- accumulate, sliding_window w=5, sliding_window w=10 -- x ratio {0.2, 0.5}, RF,
jitter 0. Six cells, one Holm family.

Each cell is the paired same-seed delta (A1 final-round fixed-threshold FPR minus control final-round
fixed-threshold FPR), where the control ran under the *same* retention policy as the A1 arm. The
paired-t / permutation / CI code is imported from ``phase0_stats_recompute`` rather than
reimplemented, so the methodology is identical to s27/s28.

The job CSVs carry a ``retention`` column but no window size, so the setting is read from the
job-file name's LoopConfig tag (``_w5_fr`` / ``_w10_fr`` / none for accumulate). Only
``results/phaseA/retention/jobs`` is read -- never the frozen paper directory.

    python -m experiments.phaseA_retention_stats
"""

from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path

import pandas as pd

from experiments.phase0_stats_recompute import paired_deltas, report_cell

JOBS = Path("results/phaseA/retention/jobs")
OUT = Path("results/phaseA/retention/retention_stats.csv")
SETTINGS = ("accumulate", "sliding_window_w5", "sliding_window_w10")
RATIOS = (0.2, 0.5)
SEEDS = list(range(1, 16))
ALPHA = 0.05


def _setting(fname: str) -> str:
    m = re.search(r"_w(\d+)_fr", fname)
    return f"sliding_window_w{m.group(1)}" if m else "accumulate"


def load_all() -> pd.DataFrame:
    frames = []
    for f in glob.glob(str(JOBS / "*.csv")):
        df = pd.read_csv(f)
        df["setting"] = _setting(Path(f).name)
        # the tag and the recorded retention column must agree
        assert set(df.retention) == {"accumulate" if df.setting.iloc[0] == "accumulate" else "sliding_window"}, f
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def holm(pvals: list[float], alpha: float = ALPHA) -> list[tuple[int, float, bool]]:
    """Holm-Bonferroni step-down: rank by p, threshold alpha/(m-k+1); once one fails, all later
    ranks fail. Returns (rank, threshold, survives) per input position."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    out: list[tuple[int, float, bool]] = [(0, 0.0, False)] * m
    still = True
    for k, i in enumerate(order, start=1):
        thr = alpha / (m - k + 1)
        still = still and pvals[i] < thr
        out[i] = (k, thr, still)
    return out


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    df = load_all()
    rows = []
    for setting in SETTINGS:
        sub = df[df.setting == setting]
        for ratio in RATIOS:
            d = paired_deltas(sub, "a1", "rf", "fixed", 0.0, ratio, SEEDS, "fpr")
            r = report_cell(d, f"retention={setting} ratio={ratio}")
            r.update(family="retention29C", setting=setting, ratio=ratio, metric="delta_fpr_fixed")
            rows.append(r)
    for key in ("p_t", "p_perm"):
        for r, (rank, thr, ok) in zip(rows, holm([r[key] for r in rows])):
            r.update({f"holm_rank_{key}": rank, f"holm_threshold_{key}": thr,
                      f"holm_survives_{key}": ok and r["mean"] > 0})
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
