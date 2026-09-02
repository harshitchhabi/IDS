"""XGBoost detector.

No ``scale_pos_weight`` and no auto class balancing — see the package docstring.
``sample_weight`` is passed straight through to ``XGBClassifier.fit``.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import xgboost as xgb

from dloop.models.base import Model, ModelConfig

_DEFAULTS = dict(
    n_estimators=300,
    max_depth=6,
    learning_rate=0.1,
    subsample=1.0,
    colsample_bytree=1.0,
    tree_method="hist",
    objective="binary:logistic",
)


class XGBoostModel(Model):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        params = {**_DEFAULTS, **config.hyperparams}
        # n_jobs=1 + hist is bit-reproducible given random_state. scale_pos_weight
        # left at its default of 1 — deliberately, not an oversight.
        self.clf = xgb.XGBClassifier(
            random_state=config.seed, n_jobs=1, scale_pos_weight=1.0, **params,
        )

    def _fit_impl(self, x: np.ndarray, y: np.ndarray, sample_weight: np.ndarray) -> None:
        self.clf.fit(x, y, sample_weight=sample_weight)

    def _proba_impl(self, x: np.ndarray) -> np.ndarray:
        return self.clf.predict_proba(x)

    def _score_impl(self, x: np.ndarray) -> np.ndarray:
        return self.clf.predict_proba(x)[:, 1]

    def _save_estimator(self, path: Path) -> None:
        # joblib (not save_model): keeps the sklearn wrapper + sidecar naming
        # uniform with the other models and needs no file-extension juggling.
        joblib.dump(self.clf, path)

    def _load_estimator(self, path: Path) -> None:
        self.clf = joblib.load(path)
