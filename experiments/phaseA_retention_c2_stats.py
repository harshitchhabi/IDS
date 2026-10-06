"""Phase A item C2 (docs/phaseA/retention-c2-prereg.md): A1's fixed-threshold FPR damage under
accumulate vs. sliding_window w=5 / w=10 when the attacker's per-round volume is constant
(``budget_mode = fixed_batch``, 375 or 1500 rows/round), RF, jitter 0.

Family C2.1 (6 cells): per seed, A1 final-round FPR minus the matched control's (same retention,
same batch size). Family C2.2 (4 cells): per seed, windowed delta minus accumulate delta at the
same batch size -- the question whether windowing reduces damage. Holm within each family.

``paired_deltas`` / ``report_cell`` are imported from ``phase0_stats_recompute`` unchanged. The job
CSVs record neither window nor batch size, so both come from the job-file name's LoopConfig tag
(``_acc_b375`` / ``_w5_b1500`` ...), checked against the recorded retention and budget_mode.

    python -m experiments.phaseA_retention_c2_stats
"""

from __future__ import annotations

import argparse
import glob
import re
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.phase0_stats_recompute import paired_deltas, report_cell
from experiments.phaseA_retention_stats import holm

JOBS = Path("results/phaseA/retention-c2/jobs")
OUT = Path("results/phaseA/retention-c2/retention_c2_stats.csv")
RETENTIONS = ("acc", "w5", "w10")
BATCHES = (375, 1500)
SEEDS = list(range(1, 16))


def _tag(fname: str) -> tuple[str, int]:
    m = re.search(r"_(acc|w5|w10)_b(\d+)_vt", fname)
    assert m, fname
    return m.group(1), int(m.group(2))


def load_all() -> pd.DataFrame:
    frames = []
    for f in glob.glob(str(JOBS / "*.csv")):
        df = pd.read_csv(f)
        ret, b = _tag(Path(f).name)
        assert set(df.retention) == {"accumulate" if ret == "acc" else "sliding_window"}, f
        assert set(df.budget_mode) == {"fixed_batch"}, f
        df["ret"], df["batch"] = ret, b
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def deltas(df: pd.DataFrame, ret: str, batch: int) -> np.ndarray:
    sub = df[(df.ret == ret) & (df.batch == batch)]
    d = paired_deltas(sub, "a1", "rf", "fixed", 0.0, None, SEEDS, "fpr")
    assert len(d) == len(SEEDS), (ret, batch, len(d))   # sorted by seed, so arrays align
    return d


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    df = load_all()
    d = {(r, b): deltas(df, r, b) for r in RETENTIONS for b in BATCHES}

    fams: dict[str, list[dict]] = {"C2.1": [], "C2.2": []}
    for b in BATCHES:
        for r in RETENTIONS:
            row = report_cell(d[(r, b)], f"C2.1 {r} b={b}")
            row.update(family="C2.1", retention=r, batch=b, metric="delta_fpr_fixed")
            fams["C2.1"].append(row)
    for b in BATCHES:
        for r in ("w5", "w10"):
            row = report_cell(d[(r, b)] - d[("acc", b)], f"C2.2 {r}-acc b={b}")
            row.update(family="C2.2", retention=r, batch=b, metric="delta_fpr_window_minus_acc")
            fams["C2.2"].append(row)

    for rows in fams.values():
        for key in ("p_t", "p_perm"):
            for row, (rank, thr, ok) in zip(rows, holm([x[key] for x in rows])):
                row.update({f"holm_rank_{key}": rank, f"holm_threshold_{key}": thr,
                            f"holm_clears_{key}": ok})
    for row in fams["C2.2"]:
        if row["holm_clears_p_t"]:
            row["verdict"] = "windowing reduces damage" if row["mean"] < 0 else "windowing increases damage"
        else:
            row["verdict"] = "no reduction shown"
    pd.DataFrame(fams["C2.1"] + fams["C2.2"]).to_csv(OUT, index=False)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
