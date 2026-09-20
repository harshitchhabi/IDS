"""A1 — benign mimicry: the decoy is shown traffic that looks like production.

"Point the benign traffic generator at the honeypot instead of production"
(CLAUDE.md). The source rows are benign rows from the adversary pool; the
defender's auto-labeler will stamp them malicious. ``jitter`` perturbs each row
in the shared normalized feature space (:class:`~dloop.features.normalize.
Normalizer`) — it is a *knob*, not the result. Mimicry fidelity is what the
experiment reports: the realized nearest-neighbour distance from the poison rows
to ``trusted_eval`` benign (:func:`realized_fidelity`), in the same space and
metric as guard (c), so damage can be plotted against a dataset-independent
x-axis. ``jitter=0`` is raw dataset benign — the leftmost point.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dloop.adversary.base import Adversary, CostMetadata, batch_frame, cost_metadata
from dloop.features import schema
from dloop.features.normalize import _CLIP, Normalizer


_COST_FEATURES = ("flow_duration", "fwd_packets", "bwd_packets", "fwd_bytes", "bwd_bytes")
_COST_IDX = [schema.CANONICAL_FEATURES.index(f) for f in _COST_FEATURES]


class JitterAdversary(Adversary):
    """Rows from ``pool`` with per-feature Gaussian jitter in normalized space.

    ``true_label`` is the ground truth of the pool (0 = benign, 1 = attack).
    ``cost_padding`` (>= 1) scales the attacker-cost features (duration, packets,
    bytes) *before* jitter: the adversary's move against a cost-weighted defense
    (it makes the interaction look more expensive, and moves the row away from
    the benign it was copying). 1.0 leaves rows untouched.
    """

    def __init__(self, pool: np.ndarray, normalizer: Normalizer, jitter: float, seed: int,
                 *, true_label: int, cost_padding: float = 1.0) -> None:
        super().__init__(pool, seed)
        if jitter < 0:
            raise ValueError("jitter must be >= 0")
        if cost_padding < 1.0:
            raise ValueError("cost_padding must be >= 1")
        self.jitter = float(jitter)
        self.cost_padding = float(cost_padding)
        self._label = int(true_label)
        self._norm = normalizer

    def generate_batch(self, round_idx: int, budget: int) -> tuple[pd.DataFrame, CostMetadata]:
        x, resampled = self._take(budget)
        if self.cost_padding != 1.0 and len(x):
            x = x.copy()
            x[:, _COST_IDX] *= self.cost_padding
        if self.jitter > 0 and len(x):
            z = self._norm.transform(x).astype("float64")
            rng = np.random.default_rng([self._seed, round_idx, 7919])
            z = np.clip(z + self.jitter * rng.standard_normal(z.shape), -_CLIP, _CLIP)
            # cap raw values: large jitter would otherwise overflow float32 in the
            # normalizer (and make attacker cost inf) without changing which side
            # of the +-25 clip the row lands on
            x = np.clip(np.expm1(np.minimum(z * self._norm.scale + self._norm.center, 25.0)), 0.0, 1e10)
        return batch_frame(x, self._label, resampled=resampled), cost_metadata(x)


class MimicryAdversary(JitterAdversary):
    """A1: benign rows (true label 0) that the auto-labeler will stamp malicious."""

    def __init__(self, pool_benign: np.ndarray, normalizer: Normalizer, jitter: float, seed: int,
                 *, cost_padding: float = 1.0) -> None:
        super().__init__(pool_benign, normalizer, jitter, seed, true_label=0, cost_padding=cost_padding)


class FidelityMeter:
    """Nearest-neighbour distance from poison rows to a reference benign set
    (the full ``trusted_eval`` benign), per-feature RMS in normalized space —
    identical to guard (c)'s metric. The index is built once per process."""

    def __init__(self, reference_z: np.ndarray, normalizer: Normalizer) -> None:
        from sklearn.neighbors import NearestNeighbors

        self._nn = NearestNeighbors(n_neighbors=1).fit(reference_z)
        self._norm = normalizer
        self._dim = reference_z.shape[1]

    def distances(self, x: np.ndarray, *, max_rows: int, rng: np.random.Generator) -> np.ndarray:
        if len(x) > max_rows:
            x = x[np.sort(rng.choice(len(x), max_rows, replace=False))]
        d, _ = self._nn.kneighbors(self._norm.transform(x))
        return d.ravel() / np.sqrt(self._dim)


def assert_disjoint_from_eval(source_rows: np.ndarray, eval_rows: np.ndarray) -> int:
    """Assert no pre-jitter source row is content-identical (float32) to an eval
    row. Returns the number of source rows checked."""
    def keys(a: np.ndarray) -> set:
        a = np.ascontiguousarray(np.asarray(a, dtype="float32"))
        return set(a.view(np.dtype((np.void, a.dtype.itemsize * a.shape[1]))).ravel().tolist())

    overlap = keys(source_rows) & keys(eval_rows)
    if overlap:
        raise AssertionError(f"{len(overlap)} poison source rows are identical to trusted_eval rows")
    return int(len(source_rows))


class JunkAdversary(Adversary):
    """Arbitrary junk: each feature drawn independently from the pooled marginal of
    ``pool`` (benign + attack rows together), so per-feature ranges and shapes are
    realistic but every correlation between features is destroyed. The rows resemble
    neither benign nor attack traffic; stamped malicious by the auto-labeler. This is
    the "send the honeypot arbitrary bulk volume" adversary: it tests whether volume
    alone, with no fidelity to anything, degrades the detector (DECISIONS.md 22).
    ``true_label`` is 0 only by convention: junk is not an attack.
    """

    def __init__(self, pool: np.ndarray, seed: int) -> None:
        super().__init__(pool, seed)

    def generate_batch(self, round_idx: int, budget: int) -> tuple[pd.DataFrame, CostMetadata]:
        rng = np.random.default_rng([self._seed, round_idx, 4242])
        n_pool, n_feat = self._pool.shape
        x = np.empty((budget, n_feat), dtype="float64")
        for j in range(n_feat):
            x[:, j] = self._pool[rng.integers(0, n_pool, size=budget), j]
        return batch_frame(x, 0, resampled=False), cost_metadata(x)
