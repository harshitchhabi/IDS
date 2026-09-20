"""One arm of the loop, run for ``config.rounds`` rounds.

Per round: generate batch -> auto-label -> defense hook -> retain -> cold-start
retrain -> evaluate on ``trusted_eval`` (both threshold modes, per-arm TPR).

Design points that matter for reading the results:

* **Round 0 is the seed-only model and is shared by every arm** (same data,
  same model seed), so all arms start from the identical detector.
* **The model seed varies by round** (``seed * 1000 + round``) but is the same
  across arms at a given (seed, round). A cold-start retrain on identical data
  with an identical seed is bit-identical, which would make the control's
  round-to-round variance exactly zero and useless as a noise floor; varying the
  seed by round makes the control measure the real retrain noise, while arms
  still share seeds so differences between arms are attributable to the data.
* **fixed** threshold: calibrated once on the round-0 model's own validation
  split, then held. Poison that pushes benign scores up shows as rising FPR.
* **recalibrated** threshold: re-derived every round on trusted benign at the
  target FPR. FPR is pinned by construction; damage shows as collapsing TPR.
  (Both per DECISIONS.md §5.)
* Retention and the per-round budget come from :class:`~dloop.loop.config.
  LoopConfig`. The poison ratio recorded each round is honeypot rows *retained*
  in the training set / total training rows; attacker cost is cumulative over
  everything the adversary generated, retained or not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from dloop.adversary.base import Adversary, features_of
from dloop.defense.base import DefenseHook, NoOpDefense
from dloop.loop.config import LoopConfig
from dloop.loop.data import ARMS, MIN_ARM_ROWS, LoopData
from dloop.loop.labeler import auto_label
from dloop.models import ModelConfig, make_model
from dloop.models.metrics import binary_metrics

FAST_HYPERPARAMS = {
    "rf": {"n_estimators": 25, "max_depth": 16},
    "xgboost": {"n_estimators": 60},
}


@dataclass
class ArmResult:
    rows: list[dict] = field(default_factory=list)
    poison_x: np.ndarray | None = None   # every admitted honeypot row (for fidelity)
    poison_true_label: np.ndarray | None = None


@dataclass
class _RoundBatch:
    round_idx: int
    x: np.ndarray
    y: np.ndarray
    w: np.ndarray


def run_arm(
    data: LoopData,
    adversary: Adversary | None,
    *,
    scenario: str,
    model_kind: str,
    seed: int,
    config: LoopConfig,
    defense: DefenseHook | None = None,
    hyperparams: dict | None = None,
) -> ArmResult:
    defense = defense or NoOpDefense()
    hp = hyperparams if hyperparams is not None else FAST_HYPERPARAMS[model_kind]
    budgets = config.budgets(len(data.seed_x)) if adversary is not None else [0] * config.rounds

    eval_benign = data.eval_y == 0
    attack = data.eval_y == 1
    arm_masks = {a: data.eval_arm == a for a in ARMS}
    seed_x = data.seed_x.astype("float64")
    res = ArmResult()
    retained: list[_RoundBatch] = []
    all_x: list[np.ndarray] = []
    all_true: list[np.ndarray] = []
    cum_cost = dict(flows=0, packets=0.0, bytes=0.0, duration_s=0.0)
    thr_fixed: float | None = None

    for k in range(config.rounds + 1):
        batch_row = dict(batch_flows=0, batch_packets=0.0, batch_bytes=0.0, batch_duration_s=0.0,
                         batch_admitted=True, batch_resampled=False)
        if k >= 1 and adversary is not None and budgets[k - 1] > 0:
            batch, cost = adversary.generate_batch(k, budgets[k - 1])
            stamped = auto_label(batch)
            decision = defense.apply(batch, cost, stamped)
            batch_row.update(batch_flows=cost.flows, batch_packets=cost.packets, batch_bytes=cost.bytes,
                             batch_duration_s=cost.duration_s, batch_admitted=bool(decision.admit),
                             batch_resampled=bool(batch.attrs.get("resampled", False)))
            cum_cost["flows"] += cost.flows
            cum_cost["packets"] += cost.packets
            cum_cost["bytes"] += cost.bytes
            cum_cost["duration_s"] += cost.duration_s
            if decision.admit:
                bx = features_of(batch)
                retained.append(_RoundBatch(k, bx, stamped, decision.weights))
                all_x.append(bx)
                all_true.append(batch["true_label"].to_numpy())
        if config.retention == "sliding_window":
            retained = [b for b in retained if b.round_idx > k - config.window_rounds]

        n_hp = int(sum(len(b.x) for b in retained))
        x_train = np.concatenate([seed_x] + [b.x for b in retained]) if retained else seed_x
        y_train = np.concatenate([data.seed_y] + [b.y for b in retained]) if retained else data.seed_y
        w_train = (np.concatenate([np.ones(len(data.seed_y))] + [b.w for b in retained])
                   if retained else np.ones(len(data.seed_y)))

        cfg = ModelConfig(kind=model_kind, seed=seed * 1000 + k, target_fpr=config.target_fpr,
                          hyperparams=hp)
        model = make_model(cfg).fit(x_train, y_train, sample_weight=w_train)
        scores = model.score_samples(data.eval_x)

        if k == 0:
            thr_fixed = float(model.threshold_)
        # recalibrated: the model's own conservative-under-ties rule, applied to trusted benign scores
        thr_recal = float(model._calibrate_on_scores(scores[eval_benign],
                                                     np.zeros(int(eval_benign.sum()), dtype=int)))

        for mode, thr in (("fixed", thr_fixed), ("recalibrated", thr_recal)):
            m = binary_metrics(data.eval_y, scores, thr)
            row = {
                "scenario": scenario, "model": model_kind, "seed": seed,
                "retention": config.retention, "budget_mode": config.budget_mode,
                "target_poison_ratio": config.poison_ratio, "round": k, "threshold_mode": mode,
                "threshold": thr, "n_train": int(len(y_train)), "n_honeypot": n_hp,
                "poison_ratio": n_hp / len(y_train),
                "fpr": m["fpr"], "tpr": m["tpr"], "precision": m["precision"], "f1": m["f1"],
                "auroc": m["auroc"], "tn": m["tn"], "fp": m["fp"], "fn": m["fn"], "tp": m["tp"],
                **{f"cum_{c}": v for c, v in cum_cost.items()}, **batch_row,
            }
            for arm in ARMS:
                sel = arm_masks[arm] & attack
                n_arm = int(sel.sum())
                # <500-row bar applies at arm level too: below it, no number
                row[f"tpr_{arm}"] = float(np.mean(scores[sel] >= thr)) if n_arm >= MIN_ARM_ROWS else float("nan")
                row[f"n_{arm}"] = n_arm
            res.rows.append(row)

    if all_x:
        res.poison_x = np.concatenate(all_x)
        res.poison_true_label = np.concatenate(all_true)
    return res
