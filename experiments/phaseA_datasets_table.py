"""Render docs/phaseA/datasets-results.md's per-cell tables from each dataset's stats.csv
(written by experiments.phaseA_datasets_stats), so no number in the write-up is retyped.

    python -m experiments.phaseA_datasets_table cicids-fixed unsw-nb15
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path("results/phaseA/datasets")


def _p(x: float) -> str:
    return f"{x:.2g}" if x >= 1e-4 else f"{x:.1e}"


def _bar(r) -> str:
    if r.family == "B.2":
        if r.arm == "a1":
            ok = "clears" if r.clears_both else "does not clear"
            return f"{ok} α/4 = 0.0125 by both tests"
        return "CI includes 0" if r.ci_includes_0 else "**CI excludes 0**"
    ok = "clears" if r.clears_both else "does not clear"
    tail = "" if r.damage_direction else " (opposite direction)"
    return f"{ok} Holm by both tests{tail}"


def rows(dataset: str) -> list[str]:
    df = pd.read_csv(ROOT / dataset / "stats.csv")
    out = []
    for r in df.itertuples():
        if r.family == "B.2":
            cell = f"{dataset} · B.2 · {r.arm} (j={r.jitter:g}, r=0.2) · recal ΔTPR"
        else:
            mode = "fixed ΔFPR" if r.metric == "dFPR" else "recal ΔTPR"
            cell = f"{dataset} · B.1 {r.model} · r={r.ratio:g}, j={r.jitter:g} · {mode}"
        p_perm = r.p_perm_display if isinstance(r.p_perm_display, str) else _p(r.p_perm)
        out.append(f"| {cell} | {r.n} | {r.mean:+.4f} | [{r.ci_lo:+.4f}, {r.ci_hi:+.4f}] | "
                   f"{r.t:.2f} | {_p(r.p_t)} | {p_perm} | {_bar(r)} |")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("datasets", nargs="+")
    args = ap.parse_args(argv)
    print("| cell | n | effect | 95% CI | $t$ | $p_t$ | $p_{\\rm perm}$ | vs. §29 bar |")
    print("|---|---|---|---|---|---|---|---|")
    for d in args.datasets:
        print("\n".join(rows(d)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
