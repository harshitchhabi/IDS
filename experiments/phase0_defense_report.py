"""Defense evaluation: D1 vs the undefended loop vs two generic poisoning
defenses (DECISIONS.md §20, definitions and expectations fixed before the runs).

CICIDS2017 (new calibration, ``val_min_nn_distance = 0.1``, ``cicids_recal``):
A1 at raw benign fidelity (jitter 0, the regime where A1 works). Synthetic and
CICIDS S0 measure the utility each defense costs the honest loop. Everything is a
same-seed paired difference against the control, final round, 5 seeds.

Writes ``results/phase0/defense/`` (CSVs, ``report.md``, figures).
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path("results/phase0/loop")
TAU = 0.1
MODELS = ("rf", "xgboost")
D1_DEFAULT = "d1_E8_g2"
DEFENSES = ("none", D1_DEFAULT, "loss", "knn")
LABEL = {"none": "undefended", D1_DEFAULT: "D1 (E*=8, g=2)", "loss": "loss filter", "knn": "kNN sanitize"}
COLOR = {"none": "#222222", D1_DEFAULT: "#08519c", "loss": "#d98c1f", "knn": "#2a9d8f"}
RATIOS = (0.05, 0.1, 0.2, 0.5)                 # main defended table (DECISIONS 20 amendment)
RATIOS_BY_MODEL = {"rf": RATIOS, "xgboost": RATIOS + (0.8, 0.9)}   # 0.8/0.9: XGBoost only (RF too slow)
SENS_RATIO = 0.5                                # sensitivity grid, ablations and padding run here
DAMAGE_TARGET = 0.10      # "the same damage": FPR rise of at least this, fixed threshold


def load(dirname: str, tau: float) -> pd.DataFrame:
    files = glob.glob(str(ROOT / dirname / "jobs" / "*.csv"))
    df = pd.concat((pd.read_csv(f, float_precision="round_trip") for f in files), ignore_index=True)
    if "val_min_nn_distance" not in df:
        df["val_min_nn_distance"] = 0.0
    df["val_min_nn_distance"] = df["val_min_nn_distance"].fillna(0.0)
    if "defense" not in df:
        df["defense"] = "none"
    df["defense"] = df["defense"].fillna("none")
    if "cost_padding" not in df:
        df["cost_padding"] = 1.0
    df["cost_padding"] = df["cost_padding"].fillna(1.0)
    return df[np.isclose(df["val_min_nn_distance"], tau)]


def final(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["round"] == df["round"].max()]


def sigma_control(df: pd.DataFrame, model: str, mode: str, metric: str) -> float:
    c = df[(df["scenario"] == "control") & (df["model"] == model) & (df["threshold_mode"] == mode)
           & (df["round"] >= 11)]
    return float(c[metric].std(ddof=1))


def paired(df_final: pd.DataFrame, sel: pd.Series, model: str, mode: str, metric: str) -> np.ndarray:
    """Same-seed (arm - control) differences for the rows selected by ``sel``."""
    ctrl = df_final[(df_final["scenario"] == "control") & (df_final["model"] == model)
                    & (df_final["threshold_mode"] == mode)].set_index("seed")[metric]
    arm = df_final[sel & (df_final["model"] == model) & (df_final["threshold_mode"] == mode)].set_index("seed")[metric]
    seeds = sorted(set(arm.index) & set(ctrl.index))
    return (arm.loc[seeds] - ctrl.loc[seeds]).to_numpy() if seeds else np.array([])


def pm(v: np.ndarray) -> str:
    return "" if len(v) == 0 else f"{v.mean():+.3f} +/- {v.std(ddof=1):.3f}"


def a1_sel(f: pd.DataFrame, defense: str, ratio: float, jitter: float = 0.0, pad: float = 1.0) -> pd.Series:
    return ((f["scenario"] == "a1") & (f["defense"] == defense) & np.isclose(f["target_poison_ratio"], ratio)
            & np.isclose(f["jitter"], jitter) & np.isclose(f["cost_padding"], pad))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("results/phase0/defense"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    cic_all = load("cicids_recal", TAU)
    cic = final(cic_all)
    syn_all = load("synthetic", 0.0)
    syn = final(syn_all)
    md = ["# D1 vs generic defenses (CICIDS2017 A1; S0 utility on synthetic and CICIDS)", "",
          f"New calibration (tau = {TAU}). Same-seed deltas vs control, final round, 5 seeds. "
          "Recovery = share of the undefended damage removed (only where undefended damage exceeds 2 sigma_control).", ""]

    # ---- A. A1 recovery ---------------------------------------------------------------
    rows = []
    for model in MODELS:
        for mode, metric, sgn in (("fixed", "fpr", 1), ("recalibrated", "tpr", -1)):
            sig = sigma_control(cic_all, model, mode, metric)
            for ratio in RATIOS_BY_MODEL[model]:
                base = sgn * paired(cic, a1_sel(cic, "none", ratio), model, mode, metric)
                row = {"model": model, "threshold_mode": mode, "metric": ("FPR rise" if sgn > 0 else "TPR drop"),
                       "ratio": ratio, "2sigma_control": round(2 * sig, 3), "undefended": pm(base)}
                for d in DEFENSES[1:]:
                    v = sgn * paired(cic, a1_sel(cic, d, ratio), model, mode, metric)
                    row[LABEL[d]] = pm(v)
                    row[LABEL[d] + " recovery"] = (f"{100 * (1 - v.mean() / base.mean()):.0f}%"
                                                   if len(v) and len(base) and base.mean() > 2 * sig else "")
                rows.append(row)
    ta = pd.DataFrame(rows)
    ta.to_csv(args.out / "a1_recovery.csv", index=False)
    md += ["## 1. A1 at raw benign fidelity: damage and recovery", "", ta.to_markdown(index=False), ""]

    # ---- B. overhead ------------------------------------------------------------------
    ov = cic_all[(cic_all["scenario"] == "a1") & (cic_all["n_honeypot"] > 0) & (cic_all["threshold_mode"] == "fixed")
                 & (np.isclose(cic_all["jitter"], 0.0)) & np.isclose(cic_all["cost_padding"], 1.0)
                 & (cic_all["target_poison_ratio"] <= 0.5) & cic_all["defense"].isin(DEFENSES)]
    ov = ov.groupby(["model", "defense"]).agg(defense_s_per_round=("defense_seconds", "mean"),
                                              fit_s_per_round=("fit_seconds", "mean")).reset_index()
    ov["defense_overhead_vs_fit"] = ov["defense_s_per_round"] / ov["fit_s_per_round"]
    ov.to_csv(args.out / "overhead.csv", index=False)
    md += ["## 2. Overhead (mean seconds per round over rounds with honeypot data)", "", ov.round(4).to_markdown(index=False), ""]

    # ---- C. utility: S0 --------------------------------------------------------------
    util_rows = []
    for name, df, tag in (("synthetic", syn, "synthetic"), ("CICIDS2017", cic, "cicids")):
        for model in MODELS:
            for ratio in (0.05, 0.2):
                ctrl = df[(df["scenario"] == "control") & (df["model"] == model) & (df["threshold_mode"] == "fixed")]
                for d in DEFENSES:
                    s = df[(df["scenario"] == "s0") & (df["defense"] == d) & (df["model"] == model)
                           & (df["threshold_mode"] == "fixed") & np.isclose(df["target_poison_ratio"], ratio)]
                    if not len(s):
                        continue
                    r = {"dataset": name, "model": model, "ratio": ratio, "defense": LABEL[d],
                         "fpr": round(s["fpr"].mean(), 4), "mean_hp_weight": round(s["hp_mean_weight"].mean(), 3)}
                    for arm in ("seen_both", "seed_only", "honeypot_only"):
                        r[f"tpr_{arm}"] = round(s[f"tpr_{arm}"].mean(), 3)
                        r[f"control_{arm}"] = round(ctrl[f"tpr_{arm}"].mean(), 3)
                    util_rows.append(r)
    tu = pd.DataFrame(util_rows)
    if len(tu):
        for arm in ("seen_both", "honeypot_only"):
            und = tu[tu.defense == LABEL["none"]].set_index(["dataset", "model", "ratio"])
            gain_und = und[f"tpr_{arm}"] - und[f"control_{arm}"]
            keys = list(zip(tu["dataset"], tu["model"], tu["ratio"]))
            tu[f"{arm}_gain_retained"] = [
                (f"{100 * (tu.loc[i, f'tpr_{arm}'] - tu.loc[i, f'control_{arm}']) / gain_und.loc[k]:.0f}%"
                 if k in gain_und.index and gain_und.loc[k] > 0.02 else "") for i, k in zip(tu.index, keys)]
        tu.to_csv(args.out / "utility_s0.csv", index=False)
        md += ["## 3. Utility: what each defense costs the honest loop (S0, fixed threshold, final round)", "",
               "`*_gain_retained` = share of the undefended S0 TPR gain over control that survives the defense.", "",
               tu.to_markdown(index=False), ""]

    # ---- D. D1 weights --------------------------------------------------------------
    w = cic_all[(cic_all["scenario"] == "a1") & (cic_all["defense"] == D1_DEFAULT) & (cic_all["threshold_mode"] == "fixed")
                & (cic_all["round"] == cic_all["round"].max()) & np.isclose(cic_all["jitter"], 0.0)
                & np.isclose(cic_all["cost_padding"], 1.0)]
    tw = w.groupby(["model", "target_poison_ratio"]).agg(
        mean_weight=("hp_mean_weight", "mean"), zero_weight_frac=("hp_zero_weight_frac", "mean"),
        effective_ratio=("hp_effective_ratio", "mean"), nominal_ratio=("poison_ratio", "mean")).reset_index()
    tw.to_csv(args.out / "d1_weights.csv", index=False)
    md += ["## 4. What D1 does to the poison's weight (A1, jitter 0)", "", tw.round(4).to_markdown(index=False), ""]

    # ---- E. attacker cost to the same damage ------------------------------------------
    cost_rows = []
    cols = ["cum_flows", "cum_packets", "cum_bytes", "cum_duration_s"]
    for model in MODELS:
        out = {}
        for d in ("none", D1_DEFAULT):
            pts = []
            for ratio in RATIOS_BY_MODEL[model]:
                sel = a1_sel(cic, d, ratio)
                v = paired(cic, sel, model, "fixed", "fpr")
                if len(v):
                    c = cic[sel & (cic["model"] == model) & (cic["threshold_mode"] == "fixed")][cols].mean()
                    pts.append((ratio, v.mean(), c))
            hit = [p for p in pts if p[1] >= DAMAGE_TARGET]
            out[d] = (hit[0] if hit else None, pts[-1] if pts else None)
        und, d1 = out["none"][0], out[D1_DEFAULT][0]
        row = {"model": model, "target_FPR_rise": DAMAGE_TARGET,
               "undefended_first_ratio": und[0] if und else np.nan,
               "D1_first_ratio": d1[0] if d1 else np.nan,
               "D1_max_ratio_tested": out[D1_DEFAULT][1][0] if out[D1_DEFAULT][1] else np.nan,
               "D1_max_FPR_rise": round(out[D1_DEFAULT][1][1], 3) if out[D1_DEFAULT][1] else np.nan}
        for c in cols:
            u = und[2][c] if und else np.nan
            if d1:
                row[f"{c}_undef"], row[f"{c}_D1"], row[f"{c}_x"] = u, d1[2][c], d1[2][c] / u
            else:
                lb = out[D1_DEFAULT][1][2][c] if out[D1_DEFAULT][1] else np.nan
                row[f"{c}_undef"], row[f"{c}_D1"], row[f"{c}_x"] = u, f">{lb:.3g}", f">{lb / u:.1f}" if u else ""
        cost_rows.append(row)
    tc = pd.DataFrame(cost_rows)
    tc.to_csv(args.out / "attacker_cost_to_damage.csv", index=False)
    md += ["## 5. Attacker cost to reach the same damage (fixed-threshold FPR rise >= "
           f"{DAMAGE_TARGET})", "", "`_x` = D1 cost / undefended cost; `>` = not reached at the largest tested ratio "
           "(a lower bound).", "", tc.to_markdown(index=False), ""]

    # ---- F. sensitivity ---------------------------------------------------------------
    sens = cic[(cic["scenario"] == "a1") & (cic["model"] == "xgboost") & (cic["threshold_mode"] == "fixed")
               & np.isclose(cic["target_poison_ratio"], SENS_RATIO) & np.isclose(cic["jitter"], 0.0)
               & np.isclose(cic["cost_padding"], 1.0) & cic["defense"].str.startswith("d1_")]
    grid = []
    for (e, g, comp), s in sens.groupby(["d1_estar", "d1_gamma", "d1_components"]):
        v = paired(cic, a1_sel(cic, s["defense"].iloc[0], SENS_RATIO), "xgboost", "fixed", "fpr")
        grid.append({"E_star": e, "gamma": g, "components": comp, "delta_fpr_mean": v.mean(), "delta_fpr_sd": v.std(ddof=1),
                     "n_seeds": len(v)})
    tg = pd.DataFrame(grid)
    if len(tg):
        sig = sigma_control(cic_all, "xgboost", "fixed", "fpr")
        tg["within_2sigma"] = tg["delta_fpr_mean"] <= 2 * sig
        tg.to_csv(args.out / "d1_sensitivity.csv", index=False)
        full = tg[tg["components"] == "all"]
        region = full[(full["E_star"] >= 4) & (full["gamma"] >= 1)]
        md += ["## 6. Sensitivity to the parameterisation (XGBoost, ratio 0.5, jitter 0)", "",
               f"2 sigma_control = {2 * sig:.3f}. Pre-registered criterion (DECISIONS 20): 'not sensitive' iff FPR damage stays "
               f"within 2 sigma over E* >= 4, gamma >= 1. **Criterion met: {bool(region['within_2sigma'].all())}** "
               f"({int(region['within_2sigma'].sum())}/{len(region)} configurations in the region).", "",
               tg.round(4).to_markdown(index=False), ""]

    # ---- G. padding -------------------------------------------------------------------
    pad = cic_all[(cic_all["scenario"] == "a1") & (cic_all["threshold_mode"] == "fixed") & (cic_all["model"] == "xgboost")
                  & np.isclose(cic_all["target_poison_ratio"], SENS_RATIO) & np.isclose(cic_all["jitter"], 0.0)
                  & (cic_all["round"] == cic_all["round"].max()) & cic_all["defense"].isin(["none", D1_DEFAULT])]
    prow = []
    for (d, p), s in pad.groupby(["defense", "cost_padding"]):
        v = paired(cic, a1_sel(cic, d, SENS_RATIO, 0.0, p), "xgboost", "fixed", "fpr")
        prow.append({"defense": LABEL[d], "cost_padding": p, "realized_nn_median": s["fidelity_median"].mean(),
                     "mean_hp_weight": s["hp_mean_weight"].mean(), "effective_ratio": s["hp_effective_ratio"].mean(),
                     "delta_fpr": pm(v), "delta_fpr_mean": v.mean() if len(v) else np.nan,
                     "attacker_bytes": s["cum_bytes"].mean(), "attacker_duration_s": s["cum_duration_s"].mean()})
    tp = pd.DataFrame(prow).sort_values(["defense", "cost_padding"]) if prow else pd.DataFrame()
    if len(tp):
        tp.to_csv(args.out / "cost_padding.csv", index=False)
        md += ["## 7. The adversary's move: pad the flows to buy weight (XGBoost, ratio 0.5)", "",
               tp.drop(columns=["delta_fpr_mean"]).round(4).to_markdown(index=False), ""]

    # ---- figures ----------------------------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(11, 7), dpi=140, sharex=True)
    for i, model in enumerate(MODELS):
        for j, (mode, metric, sgn, ylab) in enumerate((("fixed", "fpr", 1, "FPR rise over control"),
                                                        ("recalibrated", "tpr", -1, "TPR drop from control"))):
            ax = axes[i, j]
            sig = sigma_control(cic_all, model, mode, metric)
            ax.axhspan(-2 * sig, 2 * sig, color="#888888", alpha=0.2, lw=0)
            for d in DEFENSES:
                xs, ys, es = [], [], []
                for ratio in RATIOS_BY_MODEL[model]:
                    v = sgn * paired(cic, a1_sel(cic, d, ratio), model, mode, metric)
                    if len(v):
                        xs.append(ratio); ys.append(v.mean()); es.append(v.std(ddof=1))
                if xs:
                    ax.errorbar(xs, ys, yerr=es, color=COLOR[d], marker="o", ms=4, lw=1.6, capsize=2, label=LABEL[d])
            ax.set_xscale("log")
            ax.set_title(f"{model}: {ylab}", fontsize=9, loc="left")
            ax.set_xlabel("final poison ratio (nominal)", fontsize=8)
            ax.grid(color="#e3e3e3", lw=0.6)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
    axes[0, 0].legend(fontsize=7, frameon=False)
    fig.suptitle("A1 (raw benign fidelity) on CICIDS2017: damage under each defense (grey = +/-2 sigma of control)",
                 fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(args.out / "defense_damage_vs_ratio.png")
    plt.close(fig)

    if len(tg):
        full = tg[tg["components"] == "all"]
        es_, gs_ = sorted(full["E_star"].unique()), sorted(full["gamma"].unique())
        mat = np.full((len(gs_), len(es_)), np.nan)
        for _, r in full.iterrows():
            mat[gs_.index(r["gamma"]), es_.index(r["E_star"])] = r["delta_fpr_mean"]
        fig, ax = plt.subplots(figsize=(6.5, 3.6), dpi=140)
        im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=max(0.2, np.nanmax(mat)), aspect="auto")
        for yy in range(mat.shape[0]):
            for xx in range(mat.shape[1]):
                if not np.isnan(mat[yy, xx]):
                    ax.text(xx, yy, f"{mat[yy, xx]:+.3f}", ha="center", va="center", fontsize=8,
                            color="white" if mat[yy, xx] > 0.5 * np.nanmax(mat) else "#222222")
        ax.set_xticks(range(len(es_)), [f"{e:g}" for e in es_])
        ax.set_yticks(range(len(gs_)), [f"{g:g}" for g in gs_])
        ax.set_xlabel("saturation effort E* (multiples of a median benign flow)", fontsize=8)
        ax.set_ylabel("gamma", fontsize=8)
        ax.set_title("D1 sensitivity: A1 FPR rise (XGBoost, ratio 0.5). Undefended is ~+0.56", fontsize=9, loc="left")
        fig.colorbar(im, ax=ax, label="FPR rise over control")
        fig.tight_layout()
        fig.savefig(args.out / "d1_sensitivity.png")
        plt.close(fig)

    (args.out / "report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
