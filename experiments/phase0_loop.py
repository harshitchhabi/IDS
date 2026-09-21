"""Run the loop: control, S0 (clean), A1 (benign mimicry), across seeds.

Three arms share seeds (:mod:`dloop.loop.rounds`). Each job is one
(scenario, model, seed, jitter, poison_ratio) run of ``rounds`` rounds; jobs run
in parallel processes and each writes its own CSV under ``<out>/jobs/`` so a
restart resumes instead of recomputing. Jobs are ordered so the most informative
poison ratios finish first â€” if wall clock bites, stop early and cut ratios, not
seeds.

A1 rows carry the *realized* mimicry fidelity: the median nearest-neighbour
distance (guard-(c) metric, normalized space) from the poison rows the run
actually injected to the full trusted_eval benign set. That, not the jitter
parameter, is the dataset-independent x-axis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from dloop.adversary.clean import CleanAdversary
from dloop.adversary.mimicry import (FidelityMeter, JitterAdversary, JunkAdversary, MimicryAdversary,
                                     assert_disjoint_from_eval)
from dloop.logging_config import configure, get_logger
from dloop.defense.base import NoOpDefense
from dloop.defense.d1_cost_weighting import COMPONENTS, D1Config, D1CostWeighting
from dloop.defense.generic import KNNSanitize, LossFilter, ShareCap, UniformWeight
from dloop.loop.config import LoopConfig
from dloop.loop.data import LoopData
from dloop.loop.rounds import FAST_HYPERPARAMS, run_arm

log = get_logger("experiments.phase0_loop")

RATIOS = (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5)
RATIO_PRIORITY = {0.05: 0, 0.2: 0, 0.1: 1, 0.02: 1, 0.01: 2, 0.5: 2, 0.005: 3}
JITTERS = (0.0, 0.1, 0.2, 0.3, 0.7, 1.5)   # realized NN ~ 0.01, 0.09, 0.17, 0.25, 0.56, 1.1 on CICIDS
FIDELITY_ROWS = 2000
MAX_WORKERS = 4   # 7.7 GB machine; two OOM crashes at 9-10 workers

_DATA: LoopData | None = None
_FID: FidelityMeter | None = None


def _init_worker(data_path: str, need_fidelity: bool) -> None:
    global _DATA, _FID
    configure("WARNING")
    _DATA = LoopData.load(data_path)
    if need_fidelity:
        _FID = FidelityMeter(_DATA.normalizer.transform(_DATA.eval_benign_full_x), _DATA.normalizer)


def _loop_config(j: dict) -> LoopConfig:
    return LoopConfig(rounds=j["rounds"], retention=j["retention"], window_rounds=j["window"],
                      budget_mode=j["budget_mode"], poison_ratio=j["ratio"], batch_size=j["batch_size"],
                      label_policy="ground_truth" if j["scenario"] == "a1truth" else "auto_malicious",
                      val_min_nn_distance=j["val_tau"])


def _d1_config(j: dict) -> D1Config:
    keep = set(j["d1_components"].split(",")) if j["d1_components"] else set(COMPONENTS)
    return D1Config(e_star=j["d1_estar"], gamma=j["d1_gamma"],
                    alpha=tuple(1.0 if c in keep else 0.0 for c in COMPONENTS),
                    e_star_quantile=j["d1_quantile"] or None, reference=j["d1_ref"])


def _defense_tag(j: dict) -> str:
    if j["defense"] == "none":
        return ""
    if j["defense"] == "d1":
        return "_" + _d1_config(j).tag()
    if j["defense"] == "uniform":
        return f"_uniform_w{j['uniform_w']:g}"
    if j["defense"] == "sharecap":
        return f"_sharecap_c{j['share_cap']:g}"
    return "_" + j["defense"]


def _make_defense(j: dict):
    d = j["defense"]
    if d == "none":
        return NoOpDefense()
    if d == "d1":
        return D1CostWeighting(_DATA.seed_x, _DATA.seed_y, _d1_config(j))
    if d == "knn":
        return KNNSanitize(_DATA.seed_x, _DATA.seed_y)
    if d == "loss":
        return LossFilter()
    if d == "uniform":
        return UniformWeight(j["uniform_w"])
    if d == "sharecap":
        return ShareCap(j["share_cap"])
    raise ValueError(d)


def _job_key(j: dict) -> str:
    pad = f"_pad{j['pad']:g}" if j["pad"] != 1.0 else ""
    return (f"{j['scenario']}_{j['model']}_s{j['seed']}_j{j['jitter']}_r{j['ratio']}{pad}"
            f"{_loop_config(j).tag()}{_defense_tag(j)}")


def _run_job(j: dict) -> tuple[str, list[dict]]:
    assert _DATA is not None
    t0 = time.time()
    sc, seed = j["scenario"], j["seed"]
    if sc == "control":
        adv = None
    elif sc == "s0":
        adv = CleanAdversary(_DATA.pool_attack_x, seed)
    elif sc in ("a1", "a1truth"):
        adv = MimicryAdversary(_DATA.pool_benign_x, _DATA.normalizer, j["jitter"], seed,
                               cost_padding=j["pad"])
    elif sc == "junk":  # marginal-shuffled bulk rows stamped malicious (volume with no fidelity)
        adv = JunkAdversary(np.vstack([_DATA.pool_benign_x[::4], _DATA.pool_attack_x[::2]]), seed)
    elif sc == "s0j":   # genuine attack rows, jittered like A1's poison, labelled malicious
        adv = JitterAdversary(_DATA.pool_attack_x, _DATA.normalizer, j["jitter"], seed, true_label=1)
    else:
        raise ValueError(sc)
    defense = _make_defense(j)
    res = run_arm(_DATA, adv, scenario=sc, model_kind=j["model"], seed=seed, config=_loop_config(j),
                  defense=defense)
    extra: dict = {"jitter": j["jitter"] if sc in ("a1", "a1truth", "s0j") else float("nan"),
                   "cost_padding": j["pad"], "dataset": _DATA.name,
                   "d1_estar": j["d1_estar"] if j["defense"] == "d1" else float("nan"),
                   "d1_gamma": j["d1_gamma"] if j["defense"] == "d1" else float("nan"),
                   "d1_components": (j["d1_components"] or "all") if j["defense"] == "d1" else "",
                   "d1_quantile": j["d1_quantile"] if j["defense"] == "d1" else float("nan"),
                   "d1_reference": j["d1_ref"] if j["defense"] == "d1" else "",
                   "d1_estar_effective": getattr(defense, "e_star_effective", float("nan")),
                   "uniform_w": j["uniform_w"] if j["defense"] == "uniform" else float("nan")}
    if sc in ("a1", "a1truth") and res.poison_x is not None and _FID is not None:
        d = _FID.distances(res.poison_x, max_rows=FIDELITY_ROWS, rng=np.random.default_rng(seed))
        extra.update(fidelity_median=float(np.median(d)), fidelity_p5=float(np.percentile(d, 5)),
                     fidelity_p95=float(np.percentile(d, 95)), fidelity_n=int(len(d)))
        # ground truth: every injected row is benign
        assert int(res.poison_true_label.sum()) == 0
    for r in res.rows:
        r.update(extra)
    return _job_key(j), res.rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", choices=["cicids", "synthetic"], required=True)
    ap.add_argument("--scenarios", nargs="+", choices=["control", "s0", "a1", "s0j", "a1truth", "junk"], required=True)
    ap.add_argument("--models", nargs="+", default=["rf", "xgboost"])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--ratios", type=float, nargs="+", default=list(RATIOS))
    ap.add_argument("--jitters", type=float, nargs="+", default=list(JITTERS))
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--defense", choices=["none", "d1", "knn", "loss", "uniform", "sharecap"], default="none")
    ap.add_argument("--d1-estar", type=float, default=8.0, help="D1 saturation effort E* (default fixed in DECISIONS 20)")
    ap.add_argument("--d1-gamma", type=float, default=2.0)
    ap.add_argument("--d1-quantile", type=float, default=0.0, help="D1q: E* = this quantile of benign effort (0 = off)")
    ap.add_argument("--d1-reference", choices=["median", "fixed"], default="median",
                    help="fixed = generic unit reference, needs no trusted data")
    ap.add_argument("--share-cap", type=float, default=0.05,
                    help="effective honeypot share cap for --defense sharecap")
    ap.add_argument("--uniform-w", type=float, default=0.1, help="weight for --defense uniform")
    ap.add_argument("--d1-components", default="", help="comma list from duration_s,packets,bytes,depth (ablation)")
    ap.add_argument("--no-fidelity", action="store_true",
                    help="skip the NN fidelity meter (saves ~100 MB per worker); not for cost-padding runs")
    ap.add_argument("--val-nn-tau", type=float, default=0.0,
                    help="calibrate only on validation rows with no same-class training twin closer than this")
    ap.add_argument("--pad", type=float, default=1.0, help="A1 cost-padding factor (>= 1)")
    ap.add_argument("--retention", choices=["accumulate", "sliding_window"], default="accumulate")
    ap.add_argument("--window", type=int, default=None, help="rounds kept, for sliding_window")
    ap.add_argument("--budget-mode", choices=["fixed_ratio", "fixed_batch"], default="fixed_ratio")
    ap.add_argument("--batch-size", type=int, default=0, help="flows per round, for fixed_batch")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    configure()
    if args.workers > MAX_WORKERS:
        ap.error(f"--workers is capped at {MAX_WORKERS} (this machine has 7.7 GB and has OOM'd)")

    data_path = Path("data/loop") / f"{args.dataset}.npz"
    data = LoopData.load(data_path)
    out = args.out or Path("results/phase0/loop") / args.dataset
    (out / "jobs").mkdir(parents=True, exist_ok=True)

    # the loop must never let poison source rows coincide with trusted_eval rows
    # A1's channel: fatal. (Attack-side, used only by S0: identical feature rows can
    # legitimately appear under two different family labels — the partition's
    # per-label hash allows that — so it is recorded, not fatal.)
    n_checked = assert_disjoint_from_eval(data.pool_benign_x, data.eval_benign_full_x)
    try:
        n_checked_atk = assert_disjoint_from_eval(data.pool_attack_x, data.eval_x[data.eval_y == 1])
        atk_note = "disjoint"
    except AssertionError as e:
        n_checked_atk, atk_note = int(len(data.pool_attack_x)), str(e)
        log.warning("attack-side pool/eval overlap (cross-family, non-fatal)", detail=atk_note)

    jobs: list[dict] = []
    for sc in args.scenarios:
        for model in args.models:
            for seed in range(1, args.seeds + 1):
                if sc == "control":
                    jobs.append(dict(scenario=sc, model=model, seed=seed, jitter=0.0, ratio=0.0))
                    continue
                for ratio in (args.ratios if args.budget_mode == "fixed_ratio" else (0.0,)):
                    for jit in (args.jitters if sc in ("a1", "a1truth", "s0j") else (0.0,)):
                        jobs.append(dict(scenario=sc, model=model, seed=seed, jitter=jit, ratio=ratio))
    for j in jobs:
        j.update(rounds=args.rounds, retention=args.retention, window=args.window,
                 budget_mode=args.budget_mode, batch_size=args.batch_size,
                 val_tau=args.val_nn_tau, pad=args.pad, defense=args.defense,
                 d1_estar=args.d1_estar, d1_gamma=args.d1_gamma, d1_components=args.d1_components,
                 d1_quantile=args.d1_quantile, d1_ref=args.d1_reference, uniform_w=args.uniform_w, share_cap=args.share_cap)
        _loop_config(j)   # validate the combination up front
    jobs.sort(key=lambda j: (RATIO_PRIORITY.get(j["ratio"], 0), -j["ratio"], j["scenario"],
                             j["model"] != "rf", j["seed"], j["jitter"]))

    config = {"dataset": args.dataset, "scenarios": args.scenarios, "models": args.models,
              "seeds": args.seeds, "rounds": args.rounds, "ratios": args.ratios,
              "jitters": args.jitters, "hyperparams": FAST_HYPERPARAMS, "retention": args.retention,
              "window_rounds": args.window, "budget_mode": args.budget_mode,
              "batch_size": args.batch_size, "val_min_nn_distance": args.val_nn_tau,
              "cost_padding": args.pad, "defense": args.defense, "d1_estar": args.d1_estar,
              "d1_gamma": args.d1_gamma, "d1_components": args.d1_components,
              "d1_quantile": args.d1_quantile, "d1_reference": args.d1_reference, "uniform_w": args.uniform_w, "share_cap": args.share_cap,
              "fidelity_rows": FIDELITY_ROWS, "arm_counts": data.arm_counts(),
              "seed_rows": int(len(data.seed_x)), "eval_rows": int(len(data.eval_x)),
              "a1_poison_source_rows_checked_disjoint_from_eval_benign": n_checked,
              "attack_pool_rows_checked_vs_eval_attack": n_checked_atk,
              "attack_side_note": atk_note}
    config["config_hash"] = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    (out / f"config_{'_'.join(args.scenarios)}_{config['config_hash']}.json").write_text(
        json.dumps(config, indent=2))

    todo = [j for j in jobs if not (out / "jobs" / f"{_job_key(j)}.csv").exists()]
    log.info("loop jobs", total=len(jobs), todo=len(todo), workers=args.workers,
             config_hash=config["config_hash"])
    need_fid = bool({"a1", "a1truth"} & set(args.scenarios)) and not args.no_fidelity
    t0, done = time.time(), 0
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker,
                             initargs=(str(data_path), need_fid)) as ex:
        futs = {ex.submit(_run_job, j): j for j in todo}
        for f in as_completed(futs):
            key, rows = f.result()
            pd.DataFrame(rows).to_csv(out / "jobs" / f"{key}.csv", index=False)
            done += 1
            if done % 10 == 0 or done == len(todo):
                log.info("progress", done=done, of=len(todo), minutes=round((time.time() - t0) / 60, 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
