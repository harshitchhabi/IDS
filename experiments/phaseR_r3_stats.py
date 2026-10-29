"""Phase R item R3 statistics (DECISIONS.md §31.3), per NetFlow v2 dataset.

R3.1 and R3.2 have exactly Phase A item B's structure, so their cells come from
``experiments.phaseA_datasets_stats`` (imported, not copied): the same row filters,
the same paired t / permutation machinery from ``phase0_stats_recompute`` and the
same Holm step-down. Only the family labels and the verdict wording change.

* **R3.0** degeneracy: the prep stage's ``nn_degeneracy_by_grid.csv``, restricted to
  §31.3's grids {0.005, 0.01, 0.02, 0.05}, written out unchanged. Descriptive.
* **R3.1** damage grid, per model: 8 cells, Holm within the (dataset, model) family.
  Bar: both jitter-0 fixed-threshold dFPR cells clear Holm in the positive direction.
* **R3.2** mechanism isolation (RF, recalibrated dTPR, ratio 0.2): a1, a1truth, s0j
  (jitter 0.7) and junk (jitter 0), Bonferroni alpha/4. Secondary contrast, new in
  §31.3: a1 minus a1truth at the same seed (the control cancels), "label conflict
  does damage beyond the rows" iff negative with paired-t p < 0.05.
* **R3.3** ShareCap c = 0.05, A1 jitter 0: R = 1 - mean(dFPR_def) / mean(dFPR_none),
  fixed threshold, final round, both deltas against the same-seed control, so the
  undefended arm is R3.1's own A1 cell at the same seeds. Ratio 0.5 carries the bar;
  ratio 0.2 is descriptive. The seed-bootstrap CI on R is descriptive, as in R2.1.

"Clears Holm" means rejected by both the paired t-test and the permutation test, in
the damage direction, which is how ``phaseA_datasets_stats.verdicts`` reads the same
bar. The t-only reading is also written to the CSV.

    python -m experiments.phaseR_r3_stats --dataset nf-unsw-nb15-v2 --tau 0.1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.phase0_stats_recompute import report_cell
from experiments.phaseA_datasets_stats import SEEDS, _final, b1, b2, load_jobs, paired_deltas

R3_GRIDS = (0.005, 0.01, 0.02, 0.05)
SHARE_CAP = 0.05
R_BAR = 0.90
BOOT = 10_000
BOOT_SEED = 20261029


def defended_deltas(df: pd.DataFrame, model: str, ratio: float, tau: float,
                    cap: float = SHARE_CAP) -> tuple[np.ndarray, np.ndarray]:
    """Per-seed fixed-threshold final-round dFPR of A1 (jitter 0) under ShareCap ``cap``
    and undefended, each minus the same-seed control, on the seeds both arms have."""
    base = df[(df.model == model) & (df.threshold_mode == "fixed")
              & np.isclose(df.val_min_nn_distance.fillna(0.0), tau) & df.seed.isin(SEEDS)]
    ctrl = _final(base[(base.scenario == "control") & (base.defense.fillna("none") == "none")])
    a1 = base[(base.scenario == "a1") & np.isclose(base.target_poison_ratio, ratio)
              & np.isclose(base.jitter.fillna(0.0), 0.0) & (base.cost_padding.fillna(1.0) == 1.0)]
    none = _final(a1[a1.defense.fillna("none") == "none"])
    # job rows record the defense with its cap folded in (phase0_loop's tag, e.g. "sharecap_c0.05")
    dfd = _final(a1[a1.defense == f"sharecap_c{cap:g}"])
    seeds = sorted(set(ctrl.index) & set(none.index) & set(dfd.index))
    if len(seeds) != len(SEEDS):
        raise ValueError(f"R3.3 {model} ratio {ratio}: {len(seeds)} paired seeds, expected {len(SEEDS)}")
    d_none = np.array([none.loc[s, "fpr"] - ctrl.loc[s, "fpr"] for s in seeds])
    d_def = np.array([dfd.loc[s, "fpr"] - ctrl.loc[s, "fpr"] for s in seeds])
    return d_def, d_none


def recovery(d_def: np.ndarray, d_none: np.ndarray) -> float:
    return float(1 - d_def.mean() / d_none.mean())


def boot_ci(d_def: np.ndarray, d_none: np.ndarray) -> tuple[float, float]:
    """Seed bootstrap: resample seeds with replacement, keeping each seed's pair."""
    rng = np.random.default_rng(BOOT_SEED)
    n = len(d_def)
    idx = rng.integers(0, n, size=(BOOT, n))
    num, den = d_def[idx].mean(axis=1), d_none[idx].mean(axis=1)
    ok = den != 0
    r = 1 - num[ok] / den[ok]
    return float(np.quantile(r, 0.025)), float(np.quantile(r, 0.975))


def r31(df: pd.DataFrame, dataset: str, model: str, tau: float) -> list[dict]:
    rows = b1(df, dataset, model, tau)
    for r in rows:
        r["family"] = f"R3.1 {model}"
        r["label"] = r["label"].replace("B.1", "R3.1")
        r["clears_t"] = bool(r["holm_reject_t"] and r["damage_direction"])
    return rows


def r32(df: pd.DataFrame, dataset: str, tau: float) -> list[dict]:
    rows = b2(df, dataset, tau)
    for r in rows:
        r["family"] = "R3.2"
        r["label"] = r["label"].replace("B.2", "R3.2")
    a1 = paired_deltas(df, "a1", "rf", "recalibrated", 0.7, 0.2, tau, "tpr")
    truth = paired_deltas(df, "a1truth", "rf", "recalibrated", 0.7, 0.2, tau, "tpr")
    if len(a1) != len(truth):
        raise ValueError(f"a1 has {len(a1)} seeds, a1truth {len(truth)}: contrast is unpaired")
    r = report_cell(a1 - truth, f"R3.2 {dataset} a1 - a1truth")
    r.update(dataset=dataset, family="R3.2 secondary", model="rf", arm="a1-a1truth", ratio=0.2,
             jitter=0.7, threshold_mode="recalibrated", metric="dTPR",
             holds=bool(r["mean"] < 0 and r["p_t"] < 0.05))
    rows.append(r)
    return rows


def r33(df: pd.DataFrame, dataset: str, model: str, tau: float) -> list[dict]:
    rows = []
    for ratio in (0.2, 0.5):
        d_def, d_none = defended_deltas(df, model, ratio, tau)
        r = report_cell(d_def - d_none, f"R3.3 {dataset} {model} r={ratio} sharecap-none dFPR")
        lo, hi = boot_ci(d_def, d_none)
        r.update(dataset=dataset, family=f"R3.3 {model}", model=model, arm="a1 sharecap0.05",
                 ratio=ratio, jitter=0.0, threshold_mode="fixed", metric="dFPR(def-none)",
                 R=recovery(d_def, d_none), R_boot_lo=lo, R_boot_hi=hi,
                 mean_dfpr_def=float(d_def.mean()), mean_dfpr_none=float(d_none.mean()))
        print(f"  R={r['R']:.4f} boot95=[{lo:.4f},{hi:.4f}]")
        rows.append(r)
    return rows


def verdicts(rows: list[dict]) -> dict:
    df = pd.DataFrame(rows)
    out: dict = {}
    for model in ("rf", "xgboost"):
        cells = df[(df.family == f"R3.1 {model}") & (df.jitter == 0.0) & (df.metric == "dFPR")]
        per_ratio = {float(r.ratio): bool(r.clears_both and r.damage_direction) for r in cells.itertuples()}
        k = sum(per_ratio.values())
        v31 = "holds" if k == 2 else "does not hold" if k == 0 else "mixed"
        r05 = df[(df.family == f"R3.3 {model}") & (df.ratio == 0.5)].iloc[0]
        if not per_ratio[0.5]:
            v33 = "not evaluable"
        else:
            v33 = "holds" if r05.R >= R_BAR else "does not hold"
        out[model] = {"R3.1": v31, "R3.1_per_ratio": per_ratio, "R3.3": v33, "R3.3_R_0.5": float(r05.R)}
    m2 = df[df.family == "R3.2"]
    a1_clears = bool(m2[m2.arm == "a1"].clears_both.iloc[0])
    nulls_zero = bool(m2[m2.arm != "a1"].ci_includes_0.all())
    out["R3.2"] = "holds" if a1_clears and nulls_zero else "does not hold" if not a1_clears else "mixed"
    out["R3.2_secondary_holds"] = bool(df[df.family == "R3.2 secondary"].holds.iloc[0])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--tau", type=float, required=True)
    ap.add_argument("--root", type=Path, default=Path("results/phaseR/r3"))
    args = ap.parse_args(argv)
    out_dir = args.root / args.dataset

    deg = pd.read_csv(out_dir / "nn_degeneracy_by_grid.csv")
    grid_col = "grid" if "grid" in deg.columns else deg.columns[0]
    deg = deg[np.isclose(deg[grid_col].to_numpy()[:, None], np.array(R3_GRIDS)).any(axis=1)]
    deg.to_csv(out_dir / "r3_0_degeneracy.csv", index=False)

    df = load_jobs(out_dir / "jobs")
    rows = r31(df, args.dataset, "rf", args.tau) + r31(df, args.dataset, "xgboost", args.tau)
    rows += r32(df, args.dataset, args.tau)
    rows += r33(df, args.dataset, "rf", args.tau) + r33(df, args.dataset, "xgboost", args.tau)
    pd.DataFrame(rows).to_csv(out_dir / "stats.csv", index=False)
    v = verdicts(rows)
    (out_dir / "verdicts.json").write_text(json.dumps(v, indent=2) + "\n")
    print(json.dumps(v, indent=2))
    print(f"wrote {out_dir / 'stats.csv'}, r3_0_degeneracy.csv, verdicts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
