"""Detector service: scores each replayed flow with the *current registered model* and decides alerts.

``LiveDetector`` reloads from the model registry whenever a new version appears, so a retrain in the loop is
picked up by the very next tick. ``RecordedDetector`` is the demo-day fallback: it draws alerts from the rates
recorded for the round being replayed (no model needed), and the dashboard says so loudly.
"""

from __future__ import annotations

import numpy as np

from dloop.loop.registry import ModelRegistry

MODES = ("fixed", "recalibrated")


class LiveDetector:
    recorded = False

    def __init__(self, registry: ModelRegistry, mode: str = "fixed") -> None:
        self.registry, self.mode = registry, mode
        self.version = -1
        self._model = None
        self._row: dict | None = None
        self.refresh()

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(mode)
        self.mode = mode

    def refresh(self) -> bool:
        """Load the newest registered model if it is not the one already serving. True if it changed."""
        row = self.registry.store.latest_model()
        if row is None or row["version"] == self.version:
            return False
        cur = self.registry.current()
        if cur is None:
            return False
        self.version, self._model, self._row = cur[0], cur[1], cur[2]
        return True

    @property
    def threshold(self) -> float:
        return float(self._row["threshold_fixed" if self.mode == "fixed" else "threshold_recal"])

    def score(self, x: np.ndarray, family: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if len(x) == 0 or self._model is None:
            return np.empty(0), np.empty(0, dtype=bool)
        s = self._model.score_samples(x.astype("float64"))
        return s, s >= self.threshold


class RecordedDetector:
    recorded = True

    def __init__(self, registry: ModelRegistry, mode: str = "fixed", seed: int = 0) -> None:
        self.registry, self.mode = registry, mode
        self.version = -1
        self._row: dict | None = None
        self._rng = np.random.default_rng(seed)
        self.refresh()

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(mode)
        self.mode = mode

    def refresh(self) -> bool:
        row = self.registry.store.latest_model()
        if row is None or row["version"] == self.version:
            return False
        self.version, self._row = row["version"], row
        return True

    @property
    def threshold(self) -> float:
        return float(self._row["threshold_fixed" if self.mode == "fixed" else "threshold_recal"])

    def score(self, x: np.ndarray, family: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if len(family) == 0 or self._row is None:
            return np.empty(0), np.empty(0, dtype=bool)
        m = self._row["metrics"]["modes"][self.mode]
        p = np.array([m["fpr"] if f == "BENIGN" else m["tpr_by_family"].get(str(f), m["tpr"]) for f in family])
        alert = self._rng.random(len(family)) < p
        score = np.where(alert, 0.5 + 0.5 * self._rng.random(len(family)), 0.5 * self._rng.random(len(family)))
        return score, alert
