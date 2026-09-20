"""The one model interface every detector implements, plus the shared machinery
around it: per-round fit-on-train scaling, FPR-target threshold calibration, and
the metadata sidecar.

Subclasses implement three private hooks — ``_fit_impl``, ``_score_impl``,
``_proba_impl`` — and get ``fit`` / ``predict`` / ``predict_proba`` /
``score_samples`` / ``save`` / ``load`` / ``calibrate_threshold`` for free.

``sample_weight`` is load-bearing on every path: D1 (cost-of-influence
weighting) is dead without it, so it is never optional and never silently
dropped. See :mod:`dloop.models` for the single-weight-channel rule.
"""

from __future__ import annotations

import abc
import dataclasses
import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from dloop.features import schema
from dloop.features.normalize import Normalizer
from dloop.logging_config import get_logger
from dloop.models.determinism import seed_everything
from dloop.models.metrics import binary_metrics

log = get_logger("models.base")

ModelKind = Literal["rf", "xgboost", "autoencoder"]
ThresholdMode = Literal["fixed", "recalibrated"]

_DEFAULT_SEED = 20250903


@dataclass
class ModelConfig:
    """Everything that determines a trained model bit-for-bit.

    ``threshold_mode`` is recorded here and in the sidecar; the *loop* decides
    when to recalibrate (each round for ``recalibrated``, never after round 0
    for ``fixed``). A single model in isolation always calibrates once in
    ``fit``; both modes coincide until there is a second round.
    """

    kind: ModelKind
    seed: int = _DEFAULT_SEED
    target_fpr: float = 0.01
    threshold_mode: ThresholdMode = "fixed"
    val_fraction: float = 0.2          # carved from the training set, benign-stratified
    warm_start: bool = False           # cold-start by default; A2 will want warm
    hyperparams: dict[str, Any] = field(default_factory=dict)
    # Calibrate only on validation rows that have no same-class training twin
    # closer than this (per-feature RMS, normalized space; the guard-(c) metric).
    # On near-degenerate data the validation split is full of near-copies of
    # training rows, so calibration FPR is optimistic and the threshold too low
    # (DECISIONS.md 19). 0 = off (the original behaviour, bit-identical).
    val_min_nn_distance: float = 0.0

    def hash(self) -> str:
        d = dataclasses.asdict(self)
        if not d["val_min_nn_distance"]:
            d.pop("val_min_nn_distance")     # keep hashes of pre-existing configs stable
        blob = json.dumps(d, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass
class TrainingFingerprint:
    n_rows: int
    n_benign: int
    n_attack: int
    sha256: str

    @staticmethod
    def of(x: np.ndarray, y: np.ndarray, sample_weight: np.ndarray) -> "TrainingFingerprint":
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(x, dtype="float64").round(6).tobytes())
        h.update(np.ascontiguousarray(y, dtype="int64").tobytes())
        h.update(np.ascontiguousarray(sample_weight, dtype="float64").round(6).tobytes())
        return TrainingFingerprint(
            n_rows=int(len(y)),
            n_benign=int(np.sum(y == 0)),
            n_attack=int(np.sum(y == 1)),
            sha256=h.hexdigest(),
        )


@dataclass
class ModelMetadata:
    """The JSON sidecar written next to every model binary. Phase 3's model
    registry builds on this — keep it additive."""

    kind: ModelKind
    dloop_schema_version: str
    config_hash: str
    seed: int
    threshold: float
    threshold_mode: ThresholdMode
    target_fpr: float
    training_fingerprint: dict
    scaler: dict
    calibration_metrics: dict
    config: dict
    created_utc: str

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), indent=2, default=str)


def _sidecar_path(path: str | Path) -> Path:
    p = Path(path)
    return p.with_suffix(p.suffix + ".meta.json")


def train_val_split(
    x: np.ndarray, y: np.ndarray, w: np.ndarray, *, val_fraction: float, seed: int
) -> tuple[np.ndarray, ...]:
    """Class-stratified split. Deterministic given *seed*. Returns
    ``(x_tr, x_val, y_tr, y_val, w_tr, w_val)``."""
    rng = np.random.default_rng(seed)
    tr_idx, val_idx = [], []
    for cls in np.unique(y):
        idx = np.where(y == cls)[0]
        rng.shuffle(idx)
        cut = int(round(len(idx) * val_fraction))
        val_idx.append(idx[:cut])
        tr_idx.append(idx[cut:])
    tr = np.sort(np.concatenate(tr_idx))
    val = np.sort(np.concatenate(val_idx))
    return x[tr], x[val], y[tr], y[val], w[tr], w[val]


class Model(abc.ABC):
    """Base class. Higher ``score_samples`` == more attack-like, for every
    model (supervised probability or autoencoder reconstruction error alike),
    so one threshold rule works across all of them."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self.scaler_: Normalizer | None = None
        self.threshold_: float | None = None
        self.fingerprint_: TrainingFingerprint | None = None
        self.calibration_metrics_: dict = {}
        self.val_benign_dropped_frac_: float = 0.0
        self._fitted = False

    # ---- subclass hooks --------------------------------------------------
    @abc.abstractmethod
    def _fit_impl(self, x: np.ndarray, y: np.ndarray, sample_weight: np.ndarray) -> None:
        """Fit on already-scaled features. ``sample_weight`` is always provided
        (ones if the caller passed none) and must be honoured as true
        per-sample weights."""

    @abc.abstractmethod
    def _score_impl(self, x: np.ndarray) -> np.ndarray:
        """1-D attack-likeness score on scaled features; higher == more attack-like."""

    @abc.abstractmethod
    def _proba_impl(self, x: np.ndarray) -> np.ndarray:
        """(n, 2) array of [P(benign), P(attack)] on scaled features."""

    @abc.abstractmethod
    def _save_estimator(self, path: Path) -> None: ...

    @abc.abstractmethod
    def _load_estimator(self, path: Path) -> None: ...

    # ---- public API ----------------------------------------------------
    def fit(self, X, y, sample_weight=None) -> "Model":
        seed_everything(self.config.seed)
        X = np.ascontiguousarray(X, dtype="float64")
        y = np.asarray(y).astype(int)
        w = np.ones(len(y)) if sample_weight is None else np.asarray(sample_weight, dtype="float64")
        if w.shape != y.shape:
            raise ValueError(f"sample_weight shape {w.shape} != y shape {y.shape}")

        x_tr, x_val, y_tr, y_val, w_tr, _ = train_val_split(
            X, y, w, val_fraction=self.config.val_fraction, seed=self.config.seed
        )
        # Scaler fit on the training split ONLY (classic leak otherwise).
        self.scaler_ = Normalizer.fit(x_tr)
        self.fingerprint_ = TrainingFingerprint.of(x_tr, y_tr, w_tr)

        self._fit_impl(self.scaler_.transform(x_tr), y_tr, w_tr)
        self._fitted = True

        x_val_s = self.scaler_.transform(x_val)
        val_scores = self._score_impl(x_val_s)
        keep = self._val_rows_without_twins(x_tr, x_val_s, y_tr, y_val)
        self.threshold_ = self._calibrate_on_scores(val_scores[keep], y_val[keep])
        self.calibration_metrics_ = binary_metrics(y_val[keep], val_scores[keep], self.threshold_)
        log.info("model fitted", kind=self.config.kind, config_hash=self.config.hash(),
                 threshold=round(self.threshold_, 6),
                 val_fpr=round(self.calibration_metrics_["fpr"], 4),
                 val_tpr=round(self.calibration_metrics_["tpr"], 4))
        return self

    def _val_rows_without_twins(self, x_tr: np.ndarray, x_val_s: np.ndarray,
                                y_tr: np.ndarray, y_val: np.ndarray) -> np.ndarray:
        """Mask of validation rows to calibrate on. With ``val_min_nn_distance`` = 0
        every row (unchanged behaviour); otherwise only rows whose nearest
        same-class training row is at least that far away. Falls back to all rows
        (and records nothing dropped) if fewer than 100 benign rows would remain."""
        tau = self.config.val_min_nn_distance
        keep = np.ones(len(y_val), dtype=bool)
        if tau <= 0:
            return keep
        from sklearn.neighbors import NearestNeighbors

        x_tr_s = self.scaler_.transform(x_tr)
        for cls in (0, 1):
            tr, va = x_tr_s[y_tr == cls], np.where(y_val == cls)[0]
            if len(tr) == 0 or len(va) == 0:
                continue
            d, _ = NearestNeighbors(n_neighbors=1).fit(tr).kneighbors(x_val_s[va])
            keep[va] = (d.ravel() / np.sqrt(x_val_s.shape[1])) >= tau
        if int(np.sum(keep & (y_val == 0))) < 100:
            log.warning("too few twin-free benign validation rows; calibrating on all",
                        tau=tau, kept=int(np.sum(keep & (y_val == 0))))
            return np.ones(len(y_val), dtype=bool)
        n_ben = int(np.sum(y_val == 0))
        self.val_benign_dropped_frac_ = 1.0 - float(np.sum(keep & (y_val == 0))) / max(n_ben, 1)
        return keep

    def _require_fitted(self) -> None:
        if not self._fitted or self.scaler_ is None:
            raise RuntimeError("model is not fitted")

    def score_samples(self, X) -> np.ndarray:
        self._require_fitted()
        return self._score_impl(self.scaler_.transform(np.ascontiguousarray(X, dtype="float64")))

    def predict_proba(self, X) -> np.ndarray:
        self._require_fitted()
        return self._proba_impl(self.scaler_.transform(np.ascontiguousarray(X, dtype="float64")))

    def predict(self, X) -> np.ndarray:
        if self.threshold_ is None:
            raise RuntimeError("no calibrated threshold")
        return (self.score_samples(X) >= self.threshold_).astype(int)

    def _calibrate_on_scores(self, scores: np.ndarray, y: np.ndarray) -> float:
        """Smallest threshold whose benign false-positive rate on this set is
        <= ``target_fpr``. Conservative under ties (tree models emit discrete
        scores), so the calibration-set FPR never *exceeds* target — it lands on
        the nearest achievable operating point at or below it."""
        benign = np.sort(scores[y == 0])
        if benign.size == 0:
            raise ValueError("cannot calibrate threshold: no benign rows in validation split")
        ok = [t for t in np.unique(benign) if np.mean(benign >= t) <= self.config.target_fpr]
        if ok:
            return float(min(ok))
        return float(np.nextafter(benign[-1], np.inf))  # target below 1/n: exclude all

    def calibrate_threshold(self, X, y) -> float:
        """Recalibrate the persisted threshold on a trusted benign set (the
        ``recalibrated`` mode's per-round operation). Mutates ``self.threshold_``."""
        self._require_fitted()
        y = np.asarray(y).astype(int)
        self.threshold_ = self._calibrate_on_scores(self.score_samples(X), y)
        return self.threshold_

    # ---- persistence -------------------------------------------------
    def metadata(self) -> ModelMetadata:
        self._require_fitted()
        return ModelMetadata(
            kind=self.config.kind,
            dloop_schema_version=schema.SCHEMA_VERSION,
            config_hash=self.config.hash(),
            seed=self.config.seed,
            threshold=float(self.threshold_),
            threshold_mode=self.config.threshold_mode,
            target_fpr=self.config.target_fpr,
            training_fingerprint=dataclasses.asdict(self.fingerprint_),
            scaler=self.scaler_.as_dict(),
            calibration_metrics=self.calibration_metrics_,
            config=dataclasses.asdict(self.config),
            created_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        )

    def save(self, path: str | Path) -> None:
        self._require_fitted()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._save_estimator(path)
        _sidecar_path(path).write_text(self.metadata().to_json())
        log.info("model saved", path=str(path), sidecar=str(_sidecar_path(path)))

    @classmethod
    def load(cls, path: str | Path) -> "Model":
        path = Path(path)
        meta = json.loads(_sidecar_path(path).read_text())
        config = ModelConfig(**{k: v for k, v in meta["config"].items()})
        obj = cls(config)
        obj._load_estimator(path)
        obj.scaler_ = Normalizer.from_dict(meta["scaler"])
        obj.threshold_ = float(meta["threshold"])
        obj.calibration_metrics_ = meta["calibration_metrics"]
        fp = meta["training_fingerprint"]
        obj.fingerprint_ = TrainingFingerprint(**fp)
        obj._fitted = True
        return obj
