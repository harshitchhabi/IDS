"""Consolidated, self-describing exports of every loop run, so the results do not
live only in markdown tables and ~1,900 per-job files.

Writes ``results/phase0/export/``:

* ``rounds.csv.gz``   every per-round row of every job (all datasets, calibrations,
                      scenarios, defenses), with ``run_dir`` / ``calibration_tau`` /
                      ``job`` columns saying where it came from.
* ``summary.csv``     one row per configuration: final-round mean and sd over seeds of
                      the headline metrics, and the paired same-seed delta against the
                      control of the same run directory and calibration.
* ``damage_curve.csv`` A1 damage against the realized mimicry distance (the paper's
                      x-axis), both calibrations, with the noise floor it is read against.

Definitions match the reports: sigma_control = std of the control metric over seeds x
rounds 11-20; "clears" = mean paired final-round delta > 2 sigma_control (FPR rise for the
fixed threshold, TPR drop for the recalibrated one).
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("results/phase0/loop")
RUN_DIRS = ("cicids", "cicids_recal", "synthetic")
KEYS = ["run_dir", "calibration_tau", "scenario", "defense", "model", "threshold_mode", "jitter",
        "target_poison_ratio", "cost_padding", "label_policy", "retention", "budget_mode",
        "d1_estar", "d1_gamma", "d1_components"]
METRICS = ["fpr", "tpr", "precision", "f1", "auroc", "tpr_seen_both", "tpr_seed_only", "tpr_honeypot_only",
           "poison_ratio", "hp_effective_ratio", "hp_mean_weight", "cum_flows", "cum_packets", "cum_bytes",
           "cum_duration_s"]


def load_all() -> pd.DataFrame:
    frames = []
    for d in RUN_DIRS:
        for f in sorted(glob.glob(str(ROOT / d / "jobs" / "*.csv"))):
            df = pd.read_csv(f, float_precision="round_trip")
            df.insert(0, "job", Path(f).name)
            df.insert(0, "run_dir", d)
            frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    defaults = {"defense": "none", "val_min_nn_distance": 0.0, "cost_padding": 1.0,
                "label_policy": "auto_malicious", "retention": "accumulate", "budget_mode": "fixed_ratio",
                "d1_components": ""}
    for c, v in defaults.items():
        df[c] = df[c].fillna(v) if c in df else v
    df["calibration_tau"] = df.pop("val_min_nn_distance")
    for c in ("d1_estar", "d1_gamma", "jitter"):
        if c not in df:
            df[c] = np.nan
    return df


def sigma_control(df: pd.DataFrame) -> pd.DataFrame:
    c = df[(df["scenario"] == "control") & (df["round"] >= 11)]
    g = c.groupby(["run_dir", "calibration_tau", "model", "threshold_mode"])
    return g[["fpr", "tpr"]].std(ddof=1).rename(columns={"fpr": "sigma_control_fpr", "tpr": "sigma_control_tpr"}).reset_index()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("results/phase0/export"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    df = load_all()
    df.to_csv(args.out / "rounds.csv.gz", index=False, compression="gzip")
    print(f"rounds.csv.gz: {len(df):,} rows, {df['job'].nunique():,} jobs")

    last = df["round"].max()
    fin = df[df["round"] == last].copy()
    ctrl = (fin[fin["scenario"] == "control"].set_index(["run_dir", "calibration_tau", "model", "threshold_mode", "seed"])
            [["fpr", "tpr"]].rename(columns={"fpr": "ctrl_fpr", "tpr": "ctrl_tpr"}))
    fin = fin.join(ctrl, on=["run_dir", "calibration_tau", "model", "threshold_mode", "seed"])
    fin["delta_fpr"] = fin["fpr"] - fin["ctrl_fpr"]
    fin["delta_tpr"] = fin["tpr"] - fin["ctrl_tpr"]
    if "fidelity_median" not in fin:
        fin["fidelity_median"] = np.nan

    keys = [k for k in KEYS if k in fin]
    fin_g = fin.copy()
    for k in keys:                       # groupby drops NaN keys; make them explicit
        if fin_g[k].dtype.kind == "f":
            fin_g[k] = fin_g[k].fillna(-1.0)
        elif fin_g[k].dtype == object:
            fin_g[k] = fin_g[k].fillna("")
    agg = {"seed": "nunique"}
    for m in METRICS + ["delta_fpr", "delta_tpr", "fidelity_median"]:
        if m in fin_g:
            agg[m] = ["mean", "std"]
    s = fin_g.groupby(keys).agg(agg)
    s.columns = ["n_seeds" if c == ("seed", "nunique") else f"{c[0]}_{c[1]}" for c in s.columns]
    s = s.reset_index().merge(sigma_control(df), on=["run_dir", "calibration_tau", "model", "threshold_mode"], how="left")
    s.to_csv(args.out / "summary.csv", index=False)
    print(f"summary.csv: {len(s):,} configurations")

    a1 = s[(s["scenario"] == "a1") & (s["defense"] == "none") & (s["cost_padding"] == 1.0) & (s["run_dir"] != "synthetic")
           | ((s["scenario"] == "a1") & (s["defense"] == "none") & (s["run_dir"] == "synthetic"))].copy()
    a1["damage"] = np.where(a1["threshold_mode"] == "fixed", a1["delta_fpr_mean"], -a1["delta_tpr_mean"])
    a1["sigma_control"] = np.where(a1["threshold_mode"] == "fixed", a1["sigma_control_fpr"], a1["sigma_control_tpr"])
    a1["clears_2sigma"] = a1["damage"] > 2 * a1["sigma_control"]
    a1 = a1.rename(columns={"fidelity_median_mean": "realized_nn_median"})
    cols = ["run_dir", "calibration_tau", "model", "threshold_mode", "jitter", "realized_nn_median",
            "target_poison_ratio", "n_seeds", "damage", "delta_fpr_mean", "delta_fpr_std", "delta_tpr_mean",
            "delta_tpr_std", "sigma_control", "clears_2sigma"]
    a1[[c for c in cols if c in a1]].sort_values(
        ["run_dir", "calibration_tau", "model", "threshold_mode", "target_poison_ratio", "jitter"]
    ).to_csv(args.out / "damage_curve.csv", index=False)
    print(f"damage_curve.csv: {len(a1):,} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
