"""Feature normalization — the single source of truth for scaling flow features.

Flow features span many orders of magnitude (byte counts, microsecond
durations, single-digit flag counts), so a raw Euclidean distance is dominated
by whichever feature happens to be large. Everything that needs a *comparable*
feature space — the Phase 0 partition leakage check now, models later — goes
through :class:`Normalizer`.

Transform: ``log1p`` every feature (all are non-negative and heavy-tailed),
then robust-standardize with the median and a robust scale, and clip the result.

The scale is ``max(IQR, _SCALE_MIN)`` and the output is clipped to ``+-_CLIP``.
On real CICIDS2017 many features are near-constant in benign traffic (flag
counts are almost all zero) so their IQR is exactly zero, and dividing the
handful of non-zero rows by a 1e-9 floor explodes them — which wrecked the
autoencoder (AUROC 0.59). A flat ``_SCALE_MIN`` floor of 0.1 log-units does not
bind on any feature with real spread (so synthetic behaviour is unchanged) but
tames the near-constant CICIDS features, and the ``+-_CLIP`` clip stops a lone
extreme value from dominating a distance or a reconstruction loss regardless.
Fit on a reference set, apply everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dloop.features import schema

_SCALE_MIN = 0.1
_CLIP = 25.0


def _as_feature_array(data, features: tuple[str, ...]) -> np.ndarray:
    # float32: CICIDS2017 is millions of rows and flow summary stats do not need
    # double precision. Callers that want float64 (the models) cast their own copy.
    if isinstance(data, pd.DataFrame):
        return data[list(features)].to_numpy(dtype="float32")
    return np.asarray(data, dtype="float32")


@dataclass(frozen=True)
class Normalizer:
    features: tuple[str, ...]
    center: np.ndarray  # median of log1p(feature), per feature
    scale: np.ndarray   # IQR of log1p(feature), per feature, floored

    def transform(self, data) -> np.ndarray:
        """Transform a DataFrame (by canonical column name) or a raw ndarray
        (assumed already in canonical feature order)."""
        z = (np.log1p(_as_feature_array(data, self.features)) - self.center) / self.scale
        return np.clip(z, -_CLIP, _CLIP)

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
        # column-wise stats, one column at a time, so the O(n) sort inside
        # percentile/median never needs a full second copy of a millions-row array
        n_feat = x.shape[1]
        center = np.empty(n_feat, "float64")
        scale = np.empty(n_feat, "float64")
        for j in range(n_feat):
            col = x[:, j].astype("float64")
            q25, med, q75 = np.percentile(col, [25, 50, 75])
            center[j] = med
            scale[j] = max(q75 - q25, _SCALE_MIN)
        return cls(tuple(features), center, scale)


def fit_normalizer(df: pd.DataFrame, features: tuple[str, ...] = schema.CANONICAL_FEATURES) -> Normalizer:
    return Normalizer.fit(df, features)
