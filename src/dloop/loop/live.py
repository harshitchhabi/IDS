"""The loop, one round at a time, for the live demo.

:func:`dloop.loop.rounds.run_arm` runs a whole arm in one call; a demo needs to advance the *same* loop one
round per click, change the feed (S0 / A1) and the defense between rounds, and register each retrain as a model
version. This module does that with the same building blocks as ``run_arm`` (adversaries, auto-labeler,
defenses, ``make_model``, ``binary_metrics``, both threshold modes and the per-round model seed), and
``tests/test_live.py`` asserts that with a constant scenario and defense it reproduces ``run_arm`` row for row.
If they ever disagree, that is a bug worth investigating (CLAUDE.md): the demo must show what the paper measured.

One deliberate difference: defenses are applied **retroactively**. The demo switches the defense on after the
poison is already in the training set, so per-batch weights (``Defense.apply``) are recomputed for every retained
batch under the *current* defense and then ``sanitize`` runs on the whole set. For a defense that is constant
over a run this is identical to ``run_arm`` (weights are a pure function of the batch), and the cost recorded
per round counts only work a deployed defense would do that round (the new batch plus sanitize).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from dloop.adversary.base import CostMetadata, features_of
from dloop.adversary.clean import CleanAdversary
from dloop.adversary.mimicry import MimicryAdversary
from dloop.defense.base import Defense, NoOpDefense, TrainingView
from dloop.defense.d1_cost_weighting import D1Config, D1CostWeighting
from dloop.defense.generic import KNNSanitize, ShareCap
from dloop.loop.data import LoopData
from dloop.loop.labeler import auto_label
from dloop.loop.registry import ModelRegistry
from dloop.models import ModelConfig, make_model
from dloop.models.metrics import binary_metrics

# Settings the experiments proved (DECISIONS.md 24-25). ShareCap c=0.05: recovers ~100% at poison ratios 0.5
# and 0.9. D1q q=0.99 gamma=2: the best D1 variant on CICIDS (recovery 1.002 at 0.5, 0.987 at 0.9, retention 0.645).
SHARECAP_C = 0.05
D1_BEST = D1Config(e_star=8.0, gamma=2.0, e_star_quantile=0.99)
DEFENSES = ("off", "sharecap", "d1", "knn")
SCENARIOS = ("none", "s0", "a1")
FAST_HYPERPARAMS = {"rf": {"n_estimators": 25, "max_depth": 16}, "xgboost": {"n_estimators": 60}}


@dataclass
class _Batch:
    round_idx: int
    scenario: str
    frame: pd.DataFrame
    cost: CostMetadata
    stamped: np.ndarray
    x: np.ndarray
    weights: dict[str, np.ndarray] = field(default_factory=dict)   # cache: defense name -> apply() weights


class LiveLoop:
    def __init__(self, data: LoopData, registry: ModelRegistry, *, model_kind: str = "rf", seed: int = 1,
                 batch_size: int = 1000, val_min_nn_distance: float = 0.1, target_fpr: float = 0.01,
                 jitter: float = 0.0) -> None:
        self.data, self.registry = data, registry
        self.model_kind, self.seed, self.batch_size = model_kind, seed, batch_size
        self.val_tau, self.target_fpr, self.jitter = val_min_nn_distance, target_fpr, jitter
        self.hyper = FAST_HYPERPARAMS[model_kind]
        self._eval_benign = data.eval_y == 0
        self._defenses: dict[str, Defense] = {}
        self.reset()

    # ---- lifecycle --------------------------------------------------
    def reset(self) -> None:
        self.registry.reset()
        self.round = -1
        self.batches: list[_Batch] = []
        self.history: list[dict] = []
        self.thr_fixed: float | None = None
        self.cum_flows = 0
        d = self.data
        self._adv = {"s0": CleanAdversary(d.pool_attack_x, self.seed),
                     "a1": MimicryAdversary(d.pool_benign_x, d.normalizer, self.jitter, self.seed)}
        self.step("none", "off")   # round 0: the seed-only model, identical to run_arm's round 0

    def defense(self, name: str) -> Defense:
        if name not in self._defenses:
            d = self.data
            self._defenses[name] = {
                "off": lambda: NoOpDefense(),
                "sharecap": lambda: ShareCap(SHARECAP_C),
                "d1": lambda: D1CostWeighting(d.seed_x, d.seed_y, D1_BEST),
                "knn": lambda: KNNSanitize(d.seed_x, d.seed_y),
            }[name]()
        return self._defenses[name]

    # ---- one round --------------------------------------------------
    def step(self, scenario: str, defense_name: str) -> dict:
        if scenario not in SCENARIOS or defense_name not in DEFENSES:
            raise ValueError((scenario, defense_name))
        d, defense = self.data, self.defense(defense_name)
        self.round += 1
        k = self.round
        defense_s = 0.0
        if k >= 1 and scenario != "none":
            batch, cost = self._adv[scenario].generate_batch(k, self.batch_size)
            self.batches.append(_Batch(k, scenario, batch, cost, auto_label(batch), features_of(batch)))
            self.cum_flows += cost.flows
        for b in self.batches:
            if defense.name not in b.weights:
                t0 = time.perf_counter()
                b.weights[defense.name] = np.asarray(defense.apply(b.frame, b.cost, b.stamped).weights, float)
                if b.round_idx == k:
                    defense_s += time.perf_counter() - t0   # only this round's new batch is real work
        seed_x = d.seed_x.astype("float64")
        n_seed = len(seed_x)
        n_hp = sum(len(b.x) for b in self.batches)
        x = np.concatenate([seed_x] + [b.x for b in self.batches]) if n_hp else seed_x
        y = np.concatenate([d.seed_y] + [b.stamped for b in self.batches]) if n_hp else d.seed_y
        w = (np.concatenate([np.ones(n_seed)] + [b.weights[defense.name] for b in self.batches])
             if n_hp else np.ones(n_seed))
        is_hp = np.arange(len(y)) >= n_seed
        if n_hp:
            t0 = time.perf_counter()
            w_new = np.asarray(defense.sanitize(TrainingView(x, y, w, is_hp, k, self.seed)), float)
            defense_s += time.perf_counter() - t0
            if w_new.shape != w.shape or (w_new < 0).any():
                raise ValueError("defense.sanitize must return non-negative weights of the training-set shape")
            if not np.array_equal(w_new[:n_seed], w[:n_seed]):
                raise AssertionError("a defense changed the weight of a trusted seed_train row")
            w = w_new

        cfg = ModelConfig(kind=self.model_kind, seed=self.seed * 1000 + k, target_fpr=self.target_fpr,
                          hyperparams=self.hyper, val_min_nn_distance=self.val_tau)
        t0 = time.perf_counter()
        model = make_model(cfg).fit(x, y, sample_weight=w)
        scores = model.score_samples(d.eval_x)
        fit_s = time.perf_counter() - t0
        if k == 0:
            self.thr_fixed = float(model.threshold_)
        thr_recal = float(model._calibrate_on_scores(scores[self._eval_benign],
                                                     np.zeros(int(self._eval_benign.sum()), dtype=int)))
        attack = d.eval_y == 1
        modes = {}
        for mode, thr in (("fixed", self.thr_fixed), ("recalibrated", thr_recal)):
            m = binary_metrics(d.eval_y, scores, thr)
            fam = {str(f): float(np.mean(scores[attack & (d.eval_family == f)] >= thr))
                   for f in np.unique(d.eval_family[attack])}
            modes[mode] = {"threshold": thr, "fpr": m["fpr"], "tpr": m["tpr"], "precision": m["precision"],
                           "f1": m["f1"], "auroc": m["auroc"], "tn": m["tn"], "fp": m["fp"], "fn": m["fn"],
                           "tp": m["tp"], "tpr_by_family": fam}
        hp_w = w[is_hp]
        row = {"round": k, "scenario": scenario, "defense": defense.name, "defense_key": defense_name,
               "n_train": int(len(y)), "n_honeypot": int(n_hp), "poison_ratio": n_hp / len(y),
               "hp_effective_ratio": float(hp_w.sum() / w.sum()) if n_hp else 0.0,
               "hp_mean_weight": float(hp_w.mean()) if n_hp else None,
               "s0_rows": sum(len(b.x) for b in self.batches if b.scenario == "s0"),
               "a1_rows": sum(len(b.x) for b in self.batches if b.scenario == "a1"),
               "defense_seconds": defense_s, "fit_seconds": fit_s, "cum_flows": self.cum_flows,
               "fixed_fpr": modes["fixed"]["fpr"], "fixed_tpr": modes["fixed"]["tpr"],
               "fixed_precision": modes["fixed"]["precision"],
               "recal_fpr": modes["recalibrated"]["fpr"], "recal_tpr": modes["recalibrated"]["tpr"],
               "recal_precision": modes["recalibrated"]["precision"],
               "modes": modes}
        row["version"] = self.registry.register(
            model, scenario=scenario, defense=defense_name, round_=k, threshold_fixed=self.thr_fixed,
            threshold_recal=thr_recal, metrics=row)
        self.history.append(row)
        return row
