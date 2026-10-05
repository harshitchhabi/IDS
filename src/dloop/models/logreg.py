"""Logistic regression detector.

No ``class_weight`` — see the package docstring. Influence is adjusted only
through ``sample_weight``, which sklearn's ``LogisticRegression.fit`` takes
directly.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

from dloop.models.base import Model, ModelConfig

_DEFAULTS = dict(C=1.0, max_iter=1000, solver="lbfgs")


class LogRegModel(Model):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        params = {**_DEFAULTS, **config.hyperparams}
        self.clf = LogisticRegression(random_state=config.seed, class_weight=None, **params)

    def _fit_impl(self, x: np.ndarray, y: np.ndarray, sample_weight: np.ndarray) -> None:
        self.clf.fit(x, y, sample_weight=sample_weight)

    def _proba_impl(self, x: np.ndarray) -> np.ndarray:
        p = self.clf.predict_proba(x)
        if p.shape[1] == 1:  # a class was entirely zero-weighted
            only = int(self.clf.classes_[0])
            p = np.column_stack([1 - p[:, 0], p[:, 0]]) if only == 1 else np.column_stack([p[:, 0], 1 - p[:, 0]])
        return p

    def _score_impl(self, x: np.ndarray) -> np.ndarray:
        return self._proba_impl(x)[:, 1]

    def _save_estimator(self, path: Path) -> None:
        joblib.dump(self.clf, path)

    def _load_estimator(self, path: Path) -> None:
        self.clf = joblib.load(path)
