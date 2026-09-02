"""Feature normalization — the single source of truth for scaling flow features.

Flow features span many orders of magnitude (byte counts, microsecond
durations, single-digit flag counts), so a raw Euclidean distance is dominated
by whichever feature happens to be large. Everything that needs a *comparable*
feature space — the Phase 0 partition leakage check now, models later — goes
through :class:`Normalizer`.

Transform: ``log1p`` every feature (all are non-negative and heavy-tailed),
then robust-standardize with the median and IQR (IQR floored so a near-constant
feature cannot blow up). Fit on a reference set, apply everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dloop.features import schema

_IQR_FLOOR = 1e-9


def _as_feature_array(data, features: tuple[str, ...]) -> np.ndarray:
    if isinstance(data, pd.DataFrame):
        return data[list(features)].to_numpy(dtype="float64")
    return np.asarray(data, dtype="float64")


@dataclass(frozen=True)
class Normalizer:
    features: tuple[str, ...]
    center: np.ndarray  # median of log1p(feature), per feature
    scale: np.ndarray   # IQR of log1p(feature), per feature, floored

    def transform(self, data) -> np.ndarray:
        """Transform a DataFrame (by canonical column name) or a raw ndarray
        (assumed already in canonical feature order)."""
        return (np.log1p(_as_feature_array(data, self.features)) - self.center) / self.scale

    def as_dict(self) -> dict:
        return {
            "features": list(self.features),
            "center": self.center.tolist(),
            "scale": self.scale.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Normalizer":
        return cls(tuple(d["features"]), np.asarray(d["center"]), np.asarray(d["scale"]))

    @classmethod
    def fit(cls, data, features: tuple[str, ...] = schema.CANONICAL_FEATURES) -> "Normalizer":
        """Fit on *data* only. Models call this per round on the training split
        exactly — never on anything that includes validation or eval rows."""
        x = np.log1p(_as_feature_array(data, features))
        center = np.median(x, axis=0)
        q75, q25 = np.percentile(x, [75, 25], axis=0)
        return cls(tuple(features), center, np.maximum(q75 - q25, _IQR_FLOOR))


def fit_normalizer(df: pd.DataFrame, features: tuple[str, ...] = schema.CANONICAL_FEATURES) -> Normalizer:
    return Normalizer.fit(df, features)
