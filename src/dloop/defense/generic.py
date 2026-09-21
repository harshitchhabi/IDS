"""Generic poisoning defenses, used as baselines for D1 (DECISIONS.md §20).

Both change only the weights of honeypot-derived rows; seed_train is trusted.
Hyperparameters are fixed a priori and are not tuned on A1.

* :class:`KNNSanitize` — label sanitization against the trusted labelled set. A
  honeypot row is dropped when fewer than ``agree_frac`` of its ``k`` nearest
  seed_train neighbours carry its stamped label. Stateless per batch (the reference
  set never changes), so it hooks in at ``apply``.
* :class:`LossFilter` — loss-based filtering. At each retrain an auxiliary XGBoost
  gives *out-of-fold* probabilities over the training set; honeypot rows whose
  out-of-fold probability of their stamped label is below ``min_prob`` are dropped.
  Out-of-fold because a model that memorizes its training set has low in-sample loss
  on everything it was fit to, poison included.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dloop.adversary.base import CostMetadata, features_of
from dloop.defense.base import DefenseDecision, TrainingView
from dloop.features.normalize import Normalizer


class KNNSanitize:
    name = "knn"

    def __init__(self, seed_x: np.ndarray, seed_y: np.ndarray, *, k: int = 10, agree_frac: float = 0.5) -> None:
        from sklearn.neighbors import NearestNeighbors

        self.k, self.agree_frac = k, agree_frac
        self._seed_y = np.asarray(seed_y)
        self._norm = Normalizer.fit(np.asarray(seed_x))
        self._nn = NearestNeighbors(n_neighbors=k).fit(self._norm.transform(np.asarray(seed_x)))

    def apply(self, batch: pd.DataFrame, cost: CostMetadata, stamped_label: np.ndarray) -> DefenseDecision:
        _, idx = self._nn.kneighbors(self._norm.transform(features_of(batch)))
        agree = (self._seed_y[idx] == np.asarray(stamped_label)[:, None]).mean(axis=1)
        return DefenseDecision(weights=(agree >= self.agree_frac).astype("float64"), admit=True)

    def sanitize(self, view: TrainingView) -> np.ndarray:
        return view.w


class LossFilter:
    name = "loss"

    def __init__(self, *, min_prob: float = 0.1, folds: int = 3, n_estimators: int = 40, max_depth: int = 4) -> None:
        self.min_prob, self.folds = min_prob, folds
        self.n_estimators, self.max_depth = n_estimators, max_depth

    def apply(self, batch: pd.DataFrame, cost: CostMetadata, stamped_label: np.ndarray) -> DefenseDecision:
        return DefenseDecision(weights=np.ones(len(stamped_label)), admit=True)

    def sanitize(self, view: TrainingView) -> np.ndarray:
        import xgboost as xgb
        from sklearn.model_selection import StratifiedKFold

        x = Normalizer.fit(view.x).transform(view.x)
        y = view.y.astype(int)
        p_label = np.empty(len(y))
        skf = StratifiedKFold(n_splits=self.folds, shuffle=True, random_state=view.seed * 1000 + view.round_idx)
        for tr, va in skf.split(x, y):
            clf = xgb.XGBClassifier(n_estimators=self.n_estimators, max_depth=self.max_depth, n_jobs=1,
                                    tree_method="hist", random_state=view.seed * 1000 + view.round_idx)
            clf.fit(x[tr], y[tr], sample_weight=view.w[tr])
            p1 = clf.predict_proba(x[va])[:, 1]
            p_label[va] = np.where(y[va] == 1, p1, 1.0 - p1)
        w = view.w.copy()
        w[view.is_honeypot & (p_label < self.min_prob)] = 0.0
        return w


class UniformWeight:
    """No-skill baseline: every honeypot row at the same weight ``w``. Any defense that
    only trades recovery for retention along this line has learned nothing about which
    rows are poison (DECISIONS.md 24)."""

    def __init__(self, w: float) -> None:
        if not 0.0 <= w <= 1.0:
            raise ValueError("w must be in [0, 1]")
        self.w = float(w)
        self.name = f"uniform_w{w:g}"

    def apply(self, batch: pd.DataFrame, cost: CostMetadata, stamped_label: np.ndarray) -> DefenseDecision:
        return DefenseDecision(weights=np.full(len(stamped_label), self.w), admit=True)

    def sanitize(self, view: TrainingView) -> np.ndarray:
        return view.w
