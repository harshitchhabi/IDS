"""B.4 statistics and the §33 bar (honeypot realism).

Per condition (L, H) and model, a Holm family of 3 tests (a1, a1truth, junk vs
control) on fixed-threshold ΔFPR at ratio 0.5, final round, 15 seeds. a1 "clears
Holm with the null-arm rule" iff a1 is rejected under Holm by both the paired t and
the permutation test in the damage direction (ΔFPR > 0) AND each of a1truth, junk
has its 95% CI including 0. Combined with the replay fidelity (median NN vs 3× the
benign floor), it reports the §33 bar verdict. RF is primary; XGBoost alongside.
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.phase0_stats_recompute import report_cell
from experiments.phaseA_datasets_stats import holm, paired_deltas

ALPHA = 0.05
TAU = 0.1
ARMS = ("a1", "a1truth", "junk")


def load_jobs(*dirs: Path) -> pd.DataFrame:
    frames = []
    for d in dirs:
        frames += [pd.read_csv(f) for f in sorted(glob.glob(str(d / "*.csv")))]
    if not frames:
        raise FileNotFoundError(f"no job CSVs under {dirs}")
    return pd.concat(frames, ignore_index=True)


def holm_family(df: pd.DataFrame, model: str) -> list[dict]:
    """The 3-arm Holm family: fixed ΔFPR at ratio 0.5."""
    rows = []
    for arm in ARMS:
        d = paired_deltas(df, arm, model, "fixed", 0.0, 0.5, TAU, "fpr")
        r = report_cell(d, f"B.4 {model} {arm} dFPR r=0.5")
        r.update(model=model, arm=arm, metric="dFPR", ratio=0.5,
                 ci_includes_0=bool(r["ci_lo"] <= 0 <= r["ci_hi"]))
        rows.append(r)
    pt = np.array([r["p_t"] for r in rows]); pp = np.array([r["p_perm"] for r in rows])
    for key, p in (("t", pt), ("perm", pp)):
        thr, rej = holm(p)
        for r, th, rj in zip(rows, thr, rej, strict=True):
            r[f"holm_thr_{key}"] = th; r[f"holm_reject_{key}"] = bool(rj)
    for r in rows:
        r["clears_holm"] = bool(r["holm_reject_t"] and r["holm_reject_perm"] and r["mean"] > 0)
    return rows


def a1_clears_with_null_rule(rows: list[dict]) -> bool:
    by = {r["arm"]: r for r in rows}
    return bool(by["a1"]["clears_holm"]
                and by["a1truth"]["ci_includes_0"] and by["junk"]["ci_includes_0"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--realism-root", type=Path, default=Path("results/phaseB/realism"))
    ap.add_argument("--fidelity-l", type=Path, default=Path("results/phaseB/b1_fidelity_L.csv"))
    ap.add_argument("--fidelity-h", type=Path, default=Path("results/phaseB/b1_fidelity_H.csv"))
    ap.add_argument("--out", type=Path, default=Path("results/phaseB/b4_stats.csv"))
    args = ap.parse_args(argv)

    all_rows = []
    damage = {}
    for cond in ("L", "H"):
        df = load_jobs(args.realism_root / cond / "jobs")
        for model in ("rf", "xgboost"):
            fam = holm_family(df, model)
            for r in fam:
                r["condition"] = cond
            all_rows += fam
            if model == "rf":
                damage[cond] = a1_clears_with_null_rule(fam)

    out = pd.DataFrame(all_rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)

    # fidelity: replay median NN vs 3x floor, per condition
    fid = {}
    for cond, path in (("L", args.fidelity_l), ("H", args.fidelity_h)):
        if path.exists():
            f = pd.read_csv(path)
            rep = f[f.strategy == "replay"]
            if len(rep):
                row = rep.iloc[0]
                fid[cond] = {"median_nn": float(row["median_nn"]), "floor": float(row["benign_floor"]),
                             "ratio": float(row["ratio_to_floor"]), "within_3x": bool(row["ratio_to_floor"] <= 3.0)}

    print("=== B.4 fixed ΔFPR r=0.5 Holm family (RF primary) ===")
    print(out[out.model == "rf"][["condition", "arm", "mean", "ci_lo", "ci_hi", "p_t", "p_perm",
                                  "clears_holm", "ci_includes_0"]].to_string(index=False))
    print("\nreplay fidelity:", fid)
    print("RF a1 clears Holm + null-rule:", damage)

    # §33 bar
    H_fid = fid.get("H", {}).get("within_3x", False)
    L_fid = fid.get("L", {}).get("within_3x", False)
    H_dmg = damage.get("H", False)
    L_dmg = damage.get("L", False)
    H_both = H_fid and H_dmg
    L_neither = not (L_fid and L_dmg)
    if H_both and L_neither:
        verdict = "realism drives poisoning: HOLDS"
    elif (H_fid or H_dmg) and not H_both:
        verdict = "mixed (H meets exactly one of fidelity/damage)"
    else:
        verdict = "does not hold"
    print(f"\n§33 BAR: H_fidelity(<=3x)={H_fid} H_damage={H_dmg} | L_fidelity={L_fid} L_damage={L_dmg}")
    print(f"§33 VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
