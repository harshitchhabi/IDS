"""Phase R item R1 statistics (DECISIONS.md s31.1): R1.a (36-cell grid, 15 seeds, eval redrawn
per seed), R1.b (XGBoost bimodality, 30 seeds) and R1.c (RF mid-range jitters, 15 seeds), plus
the two checks session-r1.md requires before any statistic is read: reproduction of the
published cicids_recal job CSVs (R1.b, R1.c) and eval-draw pairing (R1.a).

Reuses experiments/phase0_stats_recompute.py's paired-delta extraction, paired t-test and
permutation test unchanged (s31, "Common statistical machinery"); only the families, the
direction rule and the R1.b mode counts are defined here.

Holm runs on the two-sided p of each test. A cell "clears" only if it survives Holm AND its mean
delta is negative, the damaging direction s31.1 names; a cell surviving with a positive mean is
reported as such and never counted toward a bar. That is how s26.1 read the same family, so the
n=5 status column (recomputed here from the published jobs) uses the same rule.

    python -m experiments.phaseR_r1_stats
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from experiments.phase0_stats_recompute import paired_deltas, report_cell

ROOT = Path("results/phaseR/r1")
GRID = ROOT / "grid36" / "jobs"
FIXED = ROOT / "fixed" / "jobs"
PUBLISHED = Path("results/phase0/loop/cicids_recal/jobs")
ALPHA = 0.05
JITTERS = (0.0, 0.002, 0.005, 0.01, 0.03, 0.1, 0.3, 0.7, 1.5)
RATIOS = (0.2, 0.5)
MODELS = ("rf", "xgboost")
REPRO_COLS = ("fpr", "tpr", "threshold", "tn", "fp", "fn", "tp")
PAIR_COLS = ("n_seen_both", "n_seed_only", "n_honeypot_only")
S256_ROUNDS = (2, 4, 6, 8, 10, 12, 15, 20)


def holm(pvals: list[float], alpha: float = ALPHA) -> tuple[list[float], list[bool]]:
    """Holm-Bonferroni step-down, same as experiments/phaseA_models_stats.py: each cell's own
    threshold alpha/(m-rank) and whether it survives; after the first failure all later fail."""
    m = len(pvals)
    order = np.argsort(pvals, kind="stable")
    thresholds = [0.0] * m
    survives = [False] * m
    still = True
    for rank, i in enumerate(order):
        thresholds[i] = alpha / (m - rank)
        still = still and pvals[i] <= thresholds[i]
        survives[i] = still
    return thresholds, survives


def load(path: Path, pattern: str = "*.csv") -> pd.DataFrame:
    files = glob.glob(str(path / pattern))
    if not files:
        raise SystemExit(f"no job CSVs under {path}")
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def apply_holm(fam: list[dict]) -> None:
    for key in ("p_t", "p_perm"):
        thr, ok = holm([r[key] for r in fam])
        for r, t_, o in zip(fam, thr, ok):
            r[f"holm_thr_{key}"] = t_
            r[f"holm_{key}"] = o
            r[f"clears_{key}"] = bool(o and r["mean"] < 0)


def fmt_p(r: dict) -> str:
    return r["p_perm_display"] if r["p_perm_is_bound"] else f"{r['p_perm']:.4g}"


def status(r: dict, key: str = "p_t") -> str:
    if r[f"clears_{key}"]:
        return "clears (neg)"
    if r[f"holm_{key}"]:
        return "survives, positive (not counted)"
    return "no"


# ---------------------------------------------------------------- checks

def check_reproduction(lines: list[str]) -> bool:
    """R1.b A1 seeds 1-5 and R1.c's six A1 cells seeds 1-5 (plus their controls) against the
    published job CSV of the same name: exact equality per round and threshold mode."""
    names = [f"a1_xgboost_s{s}_j0.0_r0.5_vt0.1.csv" for s in range(1, 6)]
    names += [f"a1_rf_s{s}_j{j}_r{r}_vt0.1.csv" for j in (0.01, 0.03, 0.1) for r in RATIOS
              for s in range(1, 6)]
    names += [f"control_{m}_s{s}_j0.0_r0.0_vt0.1.csv" for m in MODELS for s in range(1, 6)]
    ok_all = True
    lines.append("| job | rounds x modes | published | max abs diff | identical |")
    lines.append("|---|---:|---|---:|---|")
    for name in names:
        new, old = FIXED / name, PUBLISHED / name
        if not new.exists():
            lines.append(f"| {name} | | | | **missing new** |")
            ok_all = False
            continue
        if not old.exists():
            lines.append(f"| {name} | | absent | | not comparable |")
            continue
        a = pd.read_csv(new).sort_values(["round", "threshold_mode"]).reset_index(drop=True)
        b = pd.read_csv(old).sort_values(["round", "threshold_mode"]).reset_index(drop=True)
        same_keys = (len(a) == len(b) and (a["round"].values == b["round"].values).all()
                     and (a["threshold_mode"].values == b["threshold_mode"].values).all())
        if not same_keys:
            lines.append(f"| {name} | {len(a)} vs {len(b)} | present | | **row mismatch** |")
            ok_all = False
            continue
        diff = max(float(np.max(np.abs(a[c].values - b[c].values))) for c in REPRO_COLS)
        ident = all((a[c].values == b[c].values).all() for c in REPRO_COLS)
        ok_all &= ident
        lines.append(f"| {name} | {len(a)} | present | {diff:.3g} | {'yes' if ident else '**NO**'} |")
    return ok_all


def check_pairing(grid: pd.DataFrame, lines: list[str]) -> bool:
    """Every _evr A1 job's per-round eval composition must equal its same-seed control's."""
    g = grid.copy()
    g["n_benign"] = g["tn"] + g["fp"]
    cols = list(PAIR_COLS) + ["n_benign"]
    ctrl = g[g.scenario == "control"].set_index(["model", "seed", "round", "threshold_mode"])[cols]
    arms = g[g.scenario == "a1"]
    bad, n_jobs = [], 0
    for (model, seed, jitter, ratio), sub in arms.groupby(
            ["model", "seed", "jitter", "target_poison_ratio"]):
        n_jobs += 1
        idx = pd.MultiIndex.from_frame(sub[["model", "seed", "round", "threshold_mode"]])
        if not idx.isin(ctrl.index).all():
            bad.append(f"{model} s{seed} j{jitter} r{ratio}: control rows missing")
            continue
        c = ctrl.loc[idx].values
        if not (sub[cols].values == c).all():
            bad.append(f"{model} s{seed} j{jitter} r{ratio}")
    lines.append(f"- A1 `_evr` jobs checked: {n_jobs}; mismatches: {len(bad)}"
                 + (" (" + "; ".join(bad[:10]) + ")" if bad else ""))
    # The arm sizes are caps, so they are equal for every draw and say nothing about whether the
    # redraw happened. Instead: a seed's _evr control vs. the published fixed-draw control. The
    # training side (round-0 fixed threshold) must be identical; the eval counts must differ.
    same_thr = diff_counts = n_cmp = 0
    for model in MODELS:
        for s in range(1, 6):
            p = PUBLISHED / f"control_{model}_s{s}_j0.0_r0.0_vt0.1.csv"
            e = g[(g.scenario == "control") & (g.model == model) & (g.seed == s)
                  & (g["round"] == 0) & (g.threshold_mode == "fixed")]
            if not p.exists() or e.empty:
                continue
            b = pd.read_csv(p)
            b = b[(b["round"] == 0) & (b.threshold_mode == "fixed")].iloc[0]
            e = e.iloc[0]
            n_cmp += 1
            same_thr += int(e.threshold == b.threshold)
            diff_counts += int((e.tn, e.fp, e.fn, e.tp) != (b.tn, b.fp, b.fn, b.tp))
    lines.append(f"- redraw took effect: of {n_cmp} seed-1-5 controls, {same_thr} have the published "
                 f"round-0 fixed threshold (same training) and {diff_counts} have different eval "
                 f"confusion counts (different eval rows)")
    return not bad


# ---------------------------------------------------------------- families

def r1a(grid: pd.DataFrame, pub: pd.DataFrame, lines: list[str]) -> tuple[list[dict], dict]:
    seeds15, seeds5 = list(range(1, 16)), list(range(1, 6))
    fam, fam5, sens = [], [], []
    for model in MODELS:
        for ratio in RATIOS:
            for jitter in JITTERS:
                d = paired_deltas(grid, "a1", model, "recalibrated", jitter, ratio, seeds15, "tpr")
                r = report_cell(d, f"R1.a {model} r={ratio} j={jitter}")
                r.update(family="R1.a", model=model, ratio=ratio, jitter=jitter)
                fam.append(r)
                d5 = paired_deltas(pub, "a1", model, "recalibrated", jitter, ratio, seeds5, "tpr")
                r5 = report_cell(d5, f"s26.1 n=5 {model} r={ratio} j={jitter}")
                r5.update(model=model, ratio=ratio, jitter=jitter)
                fam5.append(r5)
                d5r = d[:5]  # seeds are sorted, so these are seeds 1-5 under the redraw
                sens.append({"model": model, "ratio": ratio, "jitter": jitter,
                             "mean_fixed_s1_5": d5.mean(), "mean_redraw_s1_5": d5r.mean(),
                             "mean_abs_fixed": np.abs(d5).mean(),
                             "mean_abs_redraw": np.abs(d5r).mean(),
                             "mean_abs_seedwise_diff": np.abs(d5 - d5r).mean()})
    apply_holm(fam)
    apply_holm(fam5)
    for r, r5 in zip(fam, fam5):
        r["n5_mean"], r["n5_t"], r["n5_p_t"] = r5["mean"], r5["t"], r5["p_t"]
        r["n5_status"] = status(r5)
        r["n5_clears"] = r5["clears_p_t"]

    lines.append("| cell (model, ratio, jitter) | n | mean ΔTPR | 95% CI | t | p_t | p_perm | "
                 "Holm thr | n=15 Holm (p_t) | n=15 Holm (p_perm) | n=5 mean | n=5 t | n=5 status |")
    lines.append("|---|---:|---:|---|---:|---:|---:|---:|---|---|---:|---:|---|")
    for r in sorted(fam, key=lambda r: r["p_t"]):
        lines.append(
            f"| {r['model']}, {r['ratio']}, {r['jitter']} | {r['n']} | {r['mean']:+.4f} | "
            f"[{r['ci_lo']:+.4f}, {r['ci_hi']:+.4f}] | {r['t']:+.2f} | {r['p_t']:.3g} | "
            f"{fmt_p(r)} | {r['holm_thr_p_t']:.5f} | {status(r)} | {status(r, 'p_perm')} | "
            f"{r['n5_mean']:+.4f} | {r['n5_t']:+.2f} | {r['n5_status']} |")
    newly = [r for r in fam if r["clears_p_t"] and not r["n5_clears"]]
    lost = [r for r in fam if r["n5_clears"] and not r["clears_p_t"]]
    pos = [r for r in fam if r["holm_p_t"] and r["mean"] > 0]
    name = lambda r: f"{r['model']} ratio {r['ratio']} jitter {r['jitter']}"  # noqa: E731
    lines.append("")
    lines.append(f"- Newly clear at n=15 (not at n=5): {', '.join(map(name, newly)) or 'none'}")
    lines.append(f"- No longer clear at n=15 (cleared at n=5): {', '.join(map(name, lost)) or 'none'}")
    lines.append(f"- Survive Holm in the positive (non-damaging) direction at n=15, not counted: "
                 f"{', '.join(map(name, pos)) or 'none'}")
    far_rf = [r for r in fam if r["model"] == "rf" and r["jitter"] >= 0.3 and r["clears_p_t"]]
    lines.append(f"- RF cells at jitter >= 0.3 that clear (consistent with s26.8, not new): "
                 f"{', '.join(map(name, far_rf)) or 'none'}")

    lines.append("\n**Eval-draw sensitivity (descriptive, not tested).** Seeds 1-5, same cell, "
                 "published fixed draw vs. this run's per-seed redraw.\n")
    lines.append("| cell | mean Δ fixed | mean Δ redraw | mean abs Δ fixed | mean abs Δ redraw | "
                 "mean abs(Δfixed − Δredraw) per seed |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for s in sens:
        lines.append(f"| {s['model']}, {s['ratio']}, {s['jitter']} | {s['mean_fixed_s1_5']:+.4f} | "
                     f"{s['mean_redraw_s1_5']:+.4f} | {s['mean_abs_fixed']:.4f} | "
                     f"{s['mean_abs_redraw']:.4f} | {s['mean_abs_seedwise_diff']:.4f} |")
    sd = pd.DataFrame(sens)
    lines.append(f"\nAcross the 36 cells: median per-seed abs(Δfixed − Δredraw) "
                 f"{sd.mean_abs_seedwise_diff.median():.4f}, max {sd.mean_abs_seedwise_diff.max():.4f}; "
                 f"median abs(mean Δ fixed − mean Δ redraw) "
                 f"{(sd.mean_fixed_s1_5 - sd.mean_redraw_s1_5).abs().median():.4f}.")
    pd.DataFrame(sens).to_csv(ROOT / "r1a_eval_draw_sensitivity.csv", index=False)

    surv = [(m, r) for m, r in (("rf", 0.2), ("rf", 0.5), ("xgboost", 0.5))]
    held = [next(c for c in fam if c["model"] == m and c["ratio"] == r and c["jitter"] == 0.0)
            ["clears_p_t"] for m, r in surv]
    verdict = "holds" if all(held) else ("does not hold" if not any(held) else "mixed")
    return fam, {"survivors": dict(zip([f"{m} {r}" for m, r in surv], held)), "verdict": verdict}


def r1b(fixed: pd.DataFrame, lines: list[str]) -> dict:
    sub = fixed[(fixed.model == "xgboost") & (fixed.threshold_mode == "fixed")]
    a1 = sub[(sub.scenario == "a1") & np.isclose(sub.jitter.fillna(0), 0)
             & np.isclose(sub.target_poison_ratio, 0.5)]
    ctrl = sub[sub.scenario == "control"]
    traj = a1.pivot_table(index="seed", columns="round", values="fpr")
    ctraj = ctrl.pivot_table(index="seed", columns="round", values="fpr")
    seeds = list(range(1, 31))
    missing = [s for s in seeds if s not in traj.index]
    if missing:
        raise SystemExit(f"R1.b seeds missing: {missing}")
    r10 = traj.loc[seeds, 10]
    mode = np.where(r10 > 0.3, "high", np.where(r10 < 0.05, "low", "intermediate"))
    counts = {k: int((mode == k).sum()) for k in ("high", "low", "intermediate")}
    ci = stats.binomtest(counts["high"], 30).proportion_ci(confidence_level=0.95, method="exact")

    lines.append("| seed | " + " | ".join(f"r{r}" for r in S256_ROUNDS) + " | mode (r10) | control r10 |")
    lines.append("|---:|" + "---:|" * len(S256_ROUNDS) + "---|---:|")
    for s, m in zip(seeds, mode):
        lines.append(f"| {s} | " + " | ".join(f"{traj.loc[s, r]:.3f}" for r in S256_ROUNDS)
                     + f" | {m} | {ctraj.loc[s, 10]:.3f} |")
    full = traj.loc[seeds, [c for c in traj.columns if 2 <= c <= 20]]
    full.insert(0, "mode_r10", mode)
    full.to_csv(ROOT / "r1b_xgboost_fpr_trajectories.csv")
    lines.append(f"\n(Every round 2-20 per seed: `{ROOT}/r1b_xgboost_fpr_trajectories.csv`.)\n")
    lines.append(f"- Mode counts at round 10 (high > 0.3, low < 0.05, intermediate otherwise): "
                 f"high {counts['high']}, low {counts['low']}, intermediate {counts['intermediate']}")
    lines.append(f"- High-mode share {counts['high']}/30 = {counts['high'] / 30:.3f}, "
                 f"Clopper-Pearson 95% CI [{ci.low:.3f}, {ci.high:.3f}]")
    lines.append(f"- Intermediate seeds: {[s for s, m in zip(seeds, mode) if m == 'intermediate']}")
    h, lo, mid = counts["high"], counts["low"], counts["intermediate"]
    if h >= 3 and lo >= 3 and mid <= 3:
        verdict = "holds"
    elif h <= 2 or lo <= 2:
        verdict = "does not hold"
    else:
        verdict = "mixed"
    return {"counts": counts, "ci": (ci.low, ci.high), "verdict": verdict}


def r1c(fixed: pd.DataFrame, lines: list[str]) -> tuple[list[dict], dict]:
    fam = []
    for ratio in RATIOS:
        for jitter in (0.01, 0.03, 0.1):
            d = paired_deltas(fixed, "a1", "rf", "recalibrated", jitter, ratio,
                              list(range(1, 16)), "tpr")
            r = report_cell(d, f"R1.c rf r={ratio} j={jitter}")
            r.update(family="R1.c", model="rf", ratio=ratio, jitter=jitter)
            fam.append(r)
    apply_holm(fam)
    lines.append("| cell (ratio, jitter) | n | mean ΔTPR | 95% CI | t | p_t | p_perm | Holm thr | "
                 "Holm (p_t) | Holm (p_perm) |")
    lines.append("|---|---:|---:|---|---:|---:|---:|---:|---|---|")
    for r in fam:
        lines.append(f"| {r['ratio']}, {r['jitter']} | {r['n']} | {r['mean']:+.4f} | "
                     f"[{r['ci_lo']:+.4f}, {r['ci_hi']:+.4f}] | {r['t']:+.2f} | {r['p_t']:.3g} | "
                     f"{fmt_p(r)} | {r['holm_thr_p_t']:.4f} | {status(r)} | {status(r, 'p_perm')} |")
    clears = {(r["ratio"], r["jitter"]): r["clears_p_t"] for r in fam}
    js = (0.01, 0.03, 0.1)
    adjacent = any(all(clears[(ra, j)] for ra in RATIOS for j in (js[i], js[i + 1]))
                   for i in range(len(js) - 1))
    if adjacent:
        verdict = "holds"
    elif not any(clears.values()):
        verdict = "does not hold"
    else:
        verdict = "mixed"
    return fam, {"clears": clears, "verdict": verdict}


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    out: list[str] = []
    fixed = load(FIXED)
    grid = load(GRID)
    pub = load(PUBLISHED, "a1_*_vt0.1.csv")
    pub = pd.concat([pub, load(PUBLISHED, "control_*_vt0.1.csv")], ignore_index=True)

    out.append("## Check 1: reproduction (R1.b, R1.c seeds 1-5 vs. published cicids_recal)\n")
    repro_ok = check_reproduction(out)
    out.append(f"\n**Reproduction: {'all identical' if repro_ok else 'MISMATCH'}.**\n")
    out.append("## Check 2: pairing (R1.a, `_evr` A1 vs. same-seed `_evr` control)\n")
    pair_ok = check_pairing(grid, out)
    out.append(f"\n**Pairing: {'all equal' if pair_ok else 'MISMATCH'}.**\n")

    out.append("## R1.a\n")
    fa, va = r1a(grid, pub, out)
    out.append(f"\nR1.a survivors at n=15: {va['survivors']} -> **{va['verdict']}**\n")
    out.append("## R1.b\n")
    vb = r1b(fixed, out)
    out.append(f"\nR1.b -> **{vb['verdict']}**\n")
    out.append("## R1.c\n")
    fc, vc = r1c(fixed, out)
    out.append(f"\nR1.c clears: {vc['clears']} -> **{vc['verdict']}**\n")

    pd.DataFrame(fa + fc).to_csv(ROOT / "stats.csv", index=False)
    (ROOT / "stats.md").write_text("\n".join(out) + "\n")
    print(f"wrote {ROOT / 'stats.md'} and {ROOT / 'stats.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
