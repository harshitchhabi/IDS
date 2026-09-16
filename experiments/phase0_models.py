"""Phase 0 model layer: train RF / XGBoost / autoencoder on the partitions,
calibrate thresholds to a target FPR, and report validation + trusted_eval
metrics under both threshold modes.

Writes to ``results/phase0/``:
  models.csv          per model x threshold-mode: threshold, val + eval metrics,
                      per-family-arm TPR
  determinism.md      two identical-seed runs match; sample_weight shifts every model
  models/<kind>.*     trained binaries (gitignored) + <kind>.*.meta.json sidecars

Stops before the adversary and the loop harness — this only establishes the
detectors and their calibrated operating points.
"""

from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stderr
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.logging_config import configure, get_logger
from dloop.models import ModelConfig, load_model, make_model
from dloop.models.metrics import binary_metrics
from dloop.sim import synthetic
from dloop.sim.dataset import load_partitions
from dloop.sim.partition import PartitionedData

log = get_logger("experiments.phase0_models")

KINDS = ("rf", "xgboost", "autoencoder")
_EXT = {"rf": ".joblib", "xgboost": ".joblib", "autoencoder": ".pt"}
TARGET_FPR = 0.01
SEED = 20250903


def _xy(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    return (df[list(schema.CANONICAL_FEATURES)].to_numpy("float64"),
            df[schema.BINARY_LABEL].to_numpy("int64"))


def _calib_threshold(scores: np.ndarray, y: np.ndarray, target_fpr: float) -> float:
    return float(np.quantile(scores[y == 0], 1.0 - target_fpr, method="higher"))


_ARMS = ("seen_both", "seed_only", "honeypot_only", "novel")


def _tpr(model, sub: pd.DataFrame, threshold: float) -> float:
    if sub.empty:
        return float("nan")
    X, _ = _xy(sub)
    return float(np.mean(model.score_samples(X) >= threshold))


_INSUFFICIENT = "insufficient rows"


def _per_arm_tpr(model, te: pd.DataFrame, threshold: float, arms: dict[str, list[str]]) -> dict:
    """Per-arm TPR, gated by the same <500-trusted_eval-row bar that
    ``eval_family_stats`` applies per family (DECISIONS.md §1): an arm's total
    row count can be dominated by a single tiny, split-artifact family (e.g.
    5 FTP-Patator rows landing in seed_only), and a TPR off that few rows is
    not a stable rate. Below the bar the cell is an explicit marker, never a
    number that looks precise but isn't."""
    te_atk = te[te[schema.BINARY_LABEL] == 1]
    out = {}
    for arm in _ARMS:
        sub = te_atk[te_atk[schema.LABEL].isin(arms[arm])]
        n = int(len(sub))
        if n == 0:
            out[f"tpr_{arm}"] = ""
        elif n < PartitionedData.MIN_FAMILY_ROWS:
            out[f"tpr_{arm}"] = _INSUFFICIENT
        else:
            out[f"tpr_{arm}"] = round(_tpr(model, sub, threshold), 4)
        out[f"n_{arm}"] = n
    return out


def _per_family_rows(model, data: PartitionedData, thr_fixed: float, thr_recal: float,
                     kind: str) -> list[dict]:
    """Per-family TPR (both threshold modes) for families with >=500 eval rows."""
    stats = data.eval_family_stats()
    te_atk = data["trusted_eval"]
    te_atk = te_atk[te_atk[schema.BINARY_LABEL] == 1]
    rows = []
    for _, r in stats[stats["reportable"]].iterrows():
        sub = te_atk[te_atk[schema.LABEL] == r["family"]]
        rows.append({
            "model": kind, "family": r["family"], "arm": r["arm"],
            "n_seed_train": r["n_seed_train"], "n_honeypot_pool": r["n_honeypot_pool"],
            "n_trusted_eval": r["n_trusted_eval"],
            "tpr_fixed": round(_tpr(model, sub, thr_fixed), 4),
            "tpr_recalibrated": round(_tpr(model, sub, thr_recal), 4),
        })
    return rows


def train_all(data: PartitionedData, out: Path) -> pd.DataFrame:
    Xtr, ytr = _xy(data["seed_train"])
    te = data["trusted_eval"]
    Xte, yte = _xy(te)
    te_benign = te[te[schema.BINARY_LABEL] == 0]
    Xte_b, yte_b = _xy(te_benign)
    arms = data.eval_family_split()

    rows = []
    family_rows = []
    (out / "models").mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        cfg = ModelConfig(kind=kind, seed=SEED, target_fpr=TARGET_FPR, threshold_mode="fixed")
        model = make_model(cfg).fit(Xtr, ytr)
        model.save(out / "models" / f"{kind}{_EXT[kind]}")

        eval_scores = model.score_samples(Xte)
        thr_fixed = model.threshold_                       # calibrated on seed_train val
        thr_recal = _calib_threshold(model.score_samples(Xte_b), yte_b, TARGET_FPR)
        family_rows += _per_family_rows(model, data, thr_fixed, thr_recal, kind)

        for mode, thr in (("fixed", thr_fixed), ("recalibrated", thr_recal)):
            m = binary_metrics(yte, eval_scores, thr)
            rows.append({
                "model": kind,
                "threshold_mode": mode,
                "threshold": round(thr, 6),
                "val_fpr": round(model.calibration_metrics_["fpr"], 4),
                "val_tpr": round(model.calibration_metrics_["tpr"], 4),
                "eval_fpr": round(m["fpr"], 4),
                "eval_tpr": round(m["tpr"], 4),
                "eval_precision": round(m["precision"], 4),
                "eval_f1": round(m["f1"], 4),
                "eval_auroc": round(m["auroc"], 4),
                **_per_arm_tpr(model, te, thr, arms),
            })
    df = pd.DataFrame(rows)
    df.to_csv(out / "models.csv", index=False)
    pd.DataFrame(family_rows).to_csv(out / "models_per_family.csv", index=False)
    return df


# Reproducibility is a property of the seeding, not of model size — use small,
# fast estimators for the determinism/weighting evidence.
_FAST = {"rf": {"n_estimators": 60}, "xgboost": {"n_estimators": 60},
         "autoencoder": {"epochs": 80}}


def _fast_cfg(kind: str, **kw) -> ModelConfig:
    return ModelConfig(kind=kind, seed=SEED, hyperparams=_FAST[kind], **kw)


def determinism_evidence(data: PartitionedData, out: Path) -> str:
    Xtr, ytr = _xy(data["seed_train"])
    Xte, _ = _xy(data["trusted_eval"])
    lines = ["# Phase 0 determinism & sample_weight evidence", "",
             "Small fast estimators (reproducibility depends on seeding, not model size).", ""]

    lines.append("## Two identical-seed runs produce identical predictions\n")
    lines.append("| model | max abs delta score_samples | thresholds equal | predictions equal |")
    lines.append("|---|---|---|---|")
    for kind in KINDS:
        a = make_model(_fast_cfg(kind)).fit(Xtr, ytr)
        b = make_model(_fast_cfg(kind)).fit(Xtr, ytr)
        sa, sb = a.score_samples(Xte), b.score_samples(Xte)
        lines.append(
            f"| {kind} | {np.max(np.abs(sa - sb)):.2e} | "
            f"{a.threshold_ == b.threshold_} | {np.array_equal(a.predict(Xte), b.predict(Xte))} |"
        )

    lines.append("\n## sample_weight changes every fitted model\n")
    lines.append("Zero-weight all attack rows (autoencoder: the high-fwd_bytes benign half); "
                 "refit; compare on trusted_eval.\n")
    lines.append("| model | mean abs delta score | predictions changed | frac flipped |")
    lines.append("|---|---|---|---|")
    for kind in KINDS:
        base = make_model(_fast_cfg(kind)).fit(Xtr, ytr)
        w = np.ones(len(ytr))
        if kind == "autoencoder":
            benign = ytr == 0
            col = schema.CANONICAL_FEATURES.index("fwd_bytes")
            w[benign & (Xtr[:, col] > np.median(Xtr[benign, col]))] = 0.0
        else:
            w[ytr == 1] = 0.0
        alt = make_model(_fast_cfg(kind)).fit(Xtr, ytr, sample_weight=w)
        sb, sa = base.score_samples(Xte), alt.score_samples(Xte)
        flipped = np.mean(base.predict(Xte) != alt.predict(Xte))
        lines.append(
            f"| {kind} | {np.mean(np.abs(sa - sb)):.4f} | "
            f"{not np.array_equal(base.predict(Xte), alt.predict(Xte))} | {flipped:.4f} |"
        )

    lines.append("\n## save / load round-trip\n")
    lines.append("| model | scores identical | threshold identical |")
    lines.append("|---|---|---|")
    for kind in KINDS:
        m = make_model(_fast_cfg(kind)).fit(Xtr, ytr)
        p = out / "models" / f"_rt_{kind}{_EXT[kind]}"
        m.save(p)
        r = load_model(p)
        same = np.array_equal(m.score_samples(Xte), r.score_samples(Xte))
        lines.append(f"| {kind} | {same} | {m.threshold_ == r.threshold_} |")
        p.unlink(); (p.with_suffix(p.suffix + ".meta.json")).unlink()

    text = "\n".join(lines) + "\n"
    (out / "determinism.md").write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["auto", "cicids", "synthetic"], default="synthetic")
    ap.add_argument("--strategy", choices=["within_day_temporal", "day_split"],
                    default="within_day_temporal")
    ap.add_argument("--out", type=Path, default=Path("results/phase0"))
    args = ap.parse_args(argv)
    configure()

    from experiments._common import partition_config

    buf = io.StringIO()
    with redirect_stderr(buf):
        data = load_partitions(source=args.source, synthetic_config=synthetic.SyntheticConfig(),
                               partition_config=partition_config(args.source, args.strategy))
    if data.leakage.leak_warning:
        print("*** guard (c) leak_warning is set on this partition — the trusted_eval "
              "metrics below reflect memorization, not held-out detection. ***\n")
    models_df = train_all(data, args.out)
    det = determinism_evidence(data, args.out)

    print("\n=== Phase 0 model layer ===\n")
    print("models.csv:")
    print(models_df.to_string(index=False))
    print("\n" + det)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
