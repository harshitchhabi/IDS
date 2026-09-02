"""Phase 0 checkpoint: feature distributions + cleaning drop report + leakage guards.

Runs the data layer end to end (load -> clean -> normalize -> partition ->
disjointness + leakage guards), then writes to ``results/phase0/``:

* ``config.json``            resolved config + hash (figures trace to this)
* ``cleaning_report.json``   per-day drop accounting + totals
* ``dropped_summary.csv``    rows dropped per day per reason (incl. near-dups)
* ``leakage_report.json``    guard (a)/(b)/(c) results; ``leak_warning`` gates S0
* ``partition_summary.csv``  rows / class balance / days per partition
* ``eval_family_split.json`` trusted_eval attack families, three-way: seen_both / seed_only / novel
* ``feature_stats.csv``      per-feature stats, per partition, per class
* ``class_feature_means.csv``per-label feature means
* ``feature_hist.png``       benign-vs-attack distribution grid
* ``feature_ecdf.png``       log-scale ECDFs for the heavy-tailed features
* ``nn_leakage.png``         guard (c): NN-distance distribution, trusted_eval->honeypot_pool

Exit code is non-zero when guard (c) raises ``leak_warning`` — an S0 improvement
measured on a leaking partition is memorization, not learning.

No external downloads: defaults to the synthetic source.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.logging_config import configure, get_logger
from dloop.sim import synthetic
from dloop.sim.dataset import load_partitions
from dloop.sim.partition import PARTITIONS, PartitionConfig, PartitionedData

log = get_logger("experiments.phase0_explore")


def _hash(blob: dict) -> str:
    return hashlib.sha256(json.dumps(blob, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _cleaning_json(data: PartitionedData) -> dict:
    per_day = {day: rep.as_dict() for day, rep in data.cleaning.items()}
    keys = ("rows_in", "rows_out", "rows_dropped_nan", "rows_dropped_negative",
            "rows_dropped_duplicate", "rows_dropped_bad_timestamp")
    totals = {k: sum(getattr(r, k) for r in data.cleaning.values()) for k in keys}
    totals["rows_dropped_total"] = totals["rows_in"] - totals["rows_out"]
    return {"per_day": per_day, "totals": totals}


def _dropped_summary(data: PartitionedData) -> pd.DataFrame:
    near = data.leakage.near_dups_removed
    rows = []
    for day, r in data.cleaning.items():
        rows.append(
            {
                "day": day,
                "rows_in": r.rows_in,
                "rows_out_clean": r.rows_out,
                "dropped_nan": r.rows_dropped_nan,
                "dropped_negative": r.rows_dropped_negative,
                "dropped_exact_dup": r.rows_dropped_duplicate,
                "dropped_bad_ts": r.rows_dropped_bad_timestamp,
                "inf_cells_replaced": sum(r.inf_cells_replaced.values()),
                "near_dups_removed": sum(near.get(day, {}).values()),
                "imbalance_ratio_out": round(r.imbalance_ratio_out, 2),
            }
        )
    return pd.DataFrame(rows)


def _feature_stats(data: PartitionedData) -> pd.DataFrame:
    rows = []
    for part in PARTITIONS:
        df = data[part]
        groups: list[tuple[str, pd.DataFrame]] = [("all", df)]
        groups += [({0: "benign", 1: "attack"}[int(k)], sub)
                   for k, sub in df.groupby(schema.BINARY_LABEL)]
        for cls, sub in groups:
            if sub.empty:
                continue
            for feat in schema.CANONICAL_FEATURES:
                col = sub[feat].to_numpy(dtype="float64")
                rows.append(
                    {
                        "partition": part, "class": cls, "feature": feat, "n": len(col),
                        "mean": float(np.mean(col)), "std": float(np.std(col)),
                        "min": float(np.min(col)), "p50": float(np.percentile(col, 50)),
                        "p99": float(np.percentile(col, 99)), "max": float(np.max(col)),
                    }
                )
    return pd.DataFrame(rows)


def _plot_hist(pooled: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    feats = schema.CANONICAL_FEATURES
    ncol = 4
    nrow = -(-len(feats) // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(4 * ncol, 2.6 * nrow))
    benign = pooled[pooled[schema.BINARY_LABEL] == 0]
    attack = pooled[pooled[schema.BINARY_LABEL] == 1]
    for ax, feat in zip(axes.flat, feats, strict=False):
        b = benign[feat].to_numpy(dtype="float64")
        a = attack[feat].to_numpy(dtype="float64")
        both = np.concatenate([b, a])
        lo, hi = np.percentile(both, [0.5, 99.5])
        bins = np.linspace(lo, hi, 40) if hi > lo else 40
        ax.hist(b, bins=bins, alpha=0.6, label="benign", color="#4C78A8", density=True)
        ax.hist(a, bins=bins, alpha=0.6, label="attack", color="#E45756", density=True)
        ax.set_title(feat, fontsize=8)
        ax.tick_params(labelsize=6)
    for ax in axes.flat[len(feats):]:
        ax.set_visible(False)
    axes.flat[0].legend(fontsize=7)
    fig.suptitle("Phase 0 feature distributions (all partitions pooled)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _plot_ecdf(pooled: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    feats = [
        "flow_duration", "fwd_bytes", "bwd_bytes", "flow_bytes_per_s",
        "flow_pkts_per_s", "flow_iat_mean", "fwd_packets", "pkt_size_avg",
    ]
    fig, axes = plt.subplots(2, 4, figsize=(16, 7))
    for ax, feat in zip(axes.flat, feats, strict=True):
        for lbl, color in [(0, "#4C78A8"), (1, "#E45756")]:
            v = pooled.loc[pooled[schema.BINARY_LABEL] == lbl, feat].to_numpy("float64")
            v = np.clip(v, 1e-6, None)
            xs = np.sort(v)
            ys = np.arange(1, len(xs) + 1) / len(xs)
            ax.plot(xs, ys, color=color, label={0: "benign", 1: "attack"}[lbl])
        ax.set_xscale("log")
        ax.set_title(feat, fontsize=9)
        ax.grid(alpha=0.3)
    axes.flat[0].legend(fontsize=8)
    fig.suptitle("Phase 0 feature ECDFs (log x, pooled)", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _plot_nn_leakage(data: PartitionedData, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.neighbors import NearestNeighbors

    te = data["trusted_eval"]
    hp = data["honeypot_pool"]
    te_atk = te[te[schema.BINARY_LABEL] == 1]
    hp_atk = hp[hp[schema.BINARY_LABEL] == 1]
    if te_atk.empty or hp_atk.empty:
        return
    n_feat = len(schema.CANONICAL_FEATURES)
    nn = NearestNeighbors(n_neighbors=1).fit(data.normalizer.transform(hp_atk))
    dist, _ = nn.kneighbors(data.normalizer.transform(te_atk))
    rms = dist.ravel() / np.sqrt(n_feat)

    fig, ax = plt.subplots(figsize=(9, 5))
    arms = {f: d["arm"] for f, d in data.leakage.nn_by_family.items()}
    for fam in sorted(te_atk[schema.LABEL].unique()):
        m = (te_atk[schema.LABEL] == fam).to_numpy()
        ax.hist(rms[m], bins=40, alpha=0.55, density=True,
                label=f"{fam} [{arms.get(fam, '?')}]")
    thr = data.config.nn_leak_p5_threshold
    ax.axvline(thr, color="k", ls="--", lw=1, label=f"p5 leak threshold = {thr}")
    ax.set_xlabel("nearest-neighbour distance to honeypot_pool attack (per-feature RMS, IQR units)")
    ax.set_ylabel("density")
    ax.set_title("Guard (c): trusted_eval attack -> nearest honeypot_pool attack")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _write_partitions_md(data: PartitionedData, cfg_hash: str, path: Path) -> None:
    lk = data.leakage
    L: list[str] = [
        "# Phase 0 partitions", "",
        f"Strategy `{data.config.strategy}`, config hash `{cfg_hash}`. "
        "Reviewable without re-running; regenerate with `make phase0-explore`.", "",
        "## Row counts per partition / class", "",
        data.summary().to_markdown(index=False), "",
        "## Row counts per partition / day / class", "",
    ]
    rows = []
    for part in PARTITIONS:
        df = data[part]
        for (day, isatk), n in df.groupby([schema.DAY, schema.BINARY_LABEL]).size().items():
            rows.append({"partition": part, "day": day,
                         "class": "attack" if isatk else "benign", "rows": int(n)})
    L += [pd.DataFrame(rows).pivot_table(index=["partition", "day"], columns="class",
                                        values="rows", fill_value=0).to_markdown(), ""]

    L += ["## Cleaning — rows dropped (CICIDS2017 gotcha list)", "",
          _dropped_summary(data).to_markdown(index=False), "",
          "Drop reasons: whitespace column names, +-Inf in the two rate features "
          "(coerced to NaN then dropped), negative Flow Duration artifacts, exact "
          "duplicate rows, unparseable timestamps.", ""]

    L += ["## Guard (a) — near-duplicate removal before splitting", "",
          "Radius-based in normalized feature space (grid "
          f"`{data.config.near_dup_grid}` per-feature RMS). The synthetic generator "
          "injects fingerprint-tight bursts into every *sustained* attack family "
          "(an automated tool emitting near-byte-identical flows); the guard must "
          "clear them or they leak across the temporal cut and let S0 pass by "
          "memorization.", ""]
    if lk.near_dups_removed:
        L.append("| day | family | rows removed |")
        L.append("|---|---|---|")
        for day, by in sorted(lk.near_dups_removed.items()):
            for fam, n in by.items():
                L.append(f"| {day} | {fam} | {n} |")
    else:
        L.append("_nothing removed_ (guard did not fire — investigate)")
    L.append("")

    L += ["## Guard (b) — temporal guard band at internal cuts", "",
          f"Rows within {data.config.boundary_buffer_seconds/2:.0f}s of a cut time "
          "dropped so a burst cannot straddle it.", "",
          "| stream | rows dropped |", "|---|---|"]
    for k, v in sorted(lk.buffer_rows_removed.items()):
        L.append(f"| {k} | {v} |")
    L.append("")

    L += ["## Guard (c) — nearest-neighbour distance, trusted_eval → honeypot_pool", "",
          "Per-feature RMS distance in normalized space, run for both classes. "
          "Concentration near zero would mean the partition leaks; "
          f"`leak_warning = {lk.leak_warning}`.", ""]
    for cls, d in lk.nn_distance.items():
        pc = ", ".join(f"{k}={v:.3f}" for k, v in d["percentiles"].items())
        L.append(f"- **{cls}**: {pc}; frac below grid = {d['frac_below_grid']:.4f}")
    L += ["", "### Per trusted_eval attack family", "",
          "| family | arm | n | min RMS | median RMS |", "|---|---|---|---|---|"]
    for fam, d in sorted(lk.nn_by_family.items()):
        L.append(f"| {fam} | {d['arm']} | {d['n']} | {d['min_rms']:.3f} | {d['median_rms']:.3f} |")
    L.append("")

    fs = data.eval_family_split()
    L += ["## trusted_eval family arms (three-way)", "",
          f"- **seen_both** (seed_train ∩ adversary pool): {fs['seen_both']}",
          f"- **seed_only** (seed_train only — A4's controlled arm): {fs['seed_only']}",
          f"- **novel** (neither — ~0 TPR expected for supervised): {fs['novel']}", ""]

    path.write_text("\n".join(L), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["auto", "cicids", "synthetic"], default="synthetic")
    parser.add_argument("--strategy", choices=["within_day_temporal", "day_split"],
                        default="within_day_temporal")
    parser.add_argument("--boundary-buffer-seconds", type=float, default=None)
    parser.add_argument("--near-dup-grid", type=float, default=None)
    parser.add_argument("--out", type=Path, default=Path("results/phase0"))
    args = parser.parse_args(argv)

    configure()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    scfg = synthetic.SyntheticConfig()
    pkw: dict = {"strategy": args.strategy}
    if args.boundary_buffer_seconds is not None:
        pkw["boundary_buffer_seconds"] = args.boundary_buffer_seconds
    if args.near_dup_grid is not None:
        pkw["near_dup_grid"] = args.near_dup_grid
    pcfg = PartitionConfig(**pkw)

    blob = {
        "source": args.source,
        "synthetic_config": dataclasses.asdict(scfg),
        "partition_config": dataclasses.asdict(pcfg),
    }
    cfg_hash = _hash(blob)
    (out / "config.json").write_text(json.dumps({**blob, "config_hash": cfg_hash}, indent=2, default=str))

    data = load_partitions(source=args.source, synthetic_config=scfg, partition_config=pcfg)
    lk = data.leakage

    (out / "cleaning_report.json").write_text(json.dumps(_cleaning_json(data), indent=2))
    (out / "leakage_report.json").write_text(json.dumps(lk.as_dict(), indent=2, default=str))
    (out / "eval_family_split.json").write_text(json.dumps(data.eval_family_split(), indent=2))
    _write_partitions_md(data, cfg_hash, out / "partitions.md")

    dropped = _dropped_summary(data)
    dropped.to_csv(out / "dropped_summary.csv", index=False)
    summary = data.summary()
    summary.to_csv(out / "partition_summary.csv", index=False)
    stats = _feature_stats(data)
    stats.to_csv(out / "feature_stats.csv", index=False)

    pooled = pd.concat([data[p] for p in PARTITIONS], ignore_index=True)
    _plot_hist(pooled, out / "feature_hist.png")
    _plot_ecdf(pooled, out / "feature_ecdf.png")
    _plot_nn_leakage(data, out / "nn_leakage.png")

    class_means = pooled.groupby(schema.LABEL)[list(schema.CANONICAL_FEATURES)].mean().T
    class_means.index.name = "feature"
    class_means.to_csv(out / "class_feature_means.csv")

    # ---- console report -----------------------------------------------------
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ct = _cleaning_json(data)["totals"]
    print("\n=== Phase 0 data layer ===")
    print(f"source={args.source}  strategy={args.strategy}  config_hash={cfg_hash}  out={out}/\n")

    print("Cleaning - rows dropped per day (CICIDS2017 gotcha list):")
    print(dropped.to_string(index=False))
    print(
        f"\n  TOTAL rows_in={ct['rows_in']}  rows_out={ct['rows_out']}  "
        f"dropped={ct['rows_dropped_total']} (nan={ct['rows_dropped_nan']}, "
        f"negative={ct['rows_dropped_negative']}, exact_dup={ct['rows_dropped_duplicate']}, "
        f"bad_ts={ct['rows_dropped_bad_timestamp']})"
    )
    if any(r.duplicate_by_class for r in data.cleaning.values()):
        merged: dict[str, int] = {}
        for r in data.cleaning.values():
            for k, v in r.duplicate_by_class.items():
                merged[k] = merged.get(k, 0) + v
        print(f"  exact duplicates by class: {merged}")

    print("\nGuard (a) near-duplicate removal (normalized grid, before splitting):")
    print(f"  {lk.near_dups_removed or 'none removed'}")
    print("Guard (b) temporal guard band rows dropped at internal cuts:")
    print(f"  {lk.buffer_rows_removed or 'none'}")

    print("\nPartitions:")
    print(summary.to_string(index=False))

    fam_split = data.eval_family_split()
    print("\ntrusted_eval attack families (three-way):")
    print(f"  seen_both (in seed_train AND adversary pool; S0 may improve TPR): {fam_split['seen_both']}")
    print(f"  seed_only (seed_train, withheld from pool; A4's arm):             {fam_split['seed_only']}")
    print(f"  novel     (in neither; ~0 TPR expected for supervised):          {fam_split['novel']}")

    print("\nGuard (c) NN distance trusted_eval -> nearest honeypot_pool row (per-feature RMS, IQR units):")
    for cls_name, d in lk.nn_distance.items():
        pc = {k: round(v, 4) for k, v in d["percentiles"].items()}
        print(f"  {cls_name:<7} percentiles: {json.dumps(pc)}  frac_below_grid={d['frac_below_grid']:.4f}")
    for fam, d in sorted(lk.nn_by_family.items()):
        print(f"    {fam:<26} n={d['n']:<5} arm={d['arm']:<10} "
              f"min={d['min_rms']:.3f} median={d['median_rms']:.3f}")

    print("\nPooled benign vs attack - mean / p50:")
    piv = stats[stats["class"].isin(["benign", "attack"])]
    piv = piv.groupby(["feature", "class"], sort=False)[["mean", "p50"]].mean().reset_index()
    wide = piv.pivot(index="feature", columns="class", values=["mean", "p50"]).reindex(
        schema.CANONICAL_FEATURES
    )
    with pd.option_context("display.float_format", lambda v: f"{v:,.2f}"):
        print(wide.to_string())

    print(f"\nFigures: {out/'feature_hist.png'}, {out/'feature_ecdf.png'}, {out/'nn_leakage.png'}")

    if lk.leak_warning:
        print("\n*** LEAKAGE WARNING (guard c) ***")
        for n in lk.notes:
            print(f"  - {n}")
        print("  The S0 checkpoint must NOT be trusted on this partition. Stop and inspect")
        print("  leakage_report.json / nn_leakage.png before running any loop.")
        return 1
    print("\nDisjointness verified (row-content across all 4 partitions; time-ordering "
          "within each day+class). No leakage warning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
