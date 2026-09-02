"""Random forest detector.

No ``class_weight`` — see the package docstring. Influence is adjusted only
through ``sample_weight``, which sklearn's ``RandomForestClassifier.fit`` takes
directly and applies during bootstrap + split scoring.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from dloop.models.base import Model, ModelConfig

_DEFAULTS = dict(n_estimators=300, max_depth=None, min_samples_leaf=2, max_features="sqrt")


class RandomForestModel(Model):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        params = {**_DEFAULTS, **config.hyperparams}
        # n_jobs=1: parallel tree building is deterministic given random_state,
        # but single-threaded removes any doubt for the bit-reproducibility claim.
        self.clf = RandomForestClassifier(
            random_state=config.seed, n_jobs=1, class_weight=None,
            warm_start=config.warm_start, **params,
        )

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
