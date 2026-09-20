"""Adversary interface: an adversary chooses the batch the decoy will see.

Phase 0 models the honeypot abstractly (CLAUDE.md): "a batch of flows the
adversary chooses, which the defender stamps malicious." An adversary is
therefore only a source of feature rows plus the *cost* of producing them; the
stamping is the labeler's job (:mod:`dloop.loop.labeler`).

Cost is recorded per batch (flows, packets, bytes, flow-time) because D1 prices
influence by exactly these quantities. ``duration_s`` is the sum of flow
durations (CICFlowMeter reports microseconds), i.e. flow-time the attacker had
to sustain, not measured wall-clock — the simulator has no wall-clock.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from dloop.features import schema

_IDX = {name: i for i, name in enumerate(schema.CANONICAL_FEATURES)}
_PACKET_COLS = (_IDX["fwd_packets"], _IDX["bwd_packets"])
_BYTE_COLS = (_IDX["fwd_bytes"], _IDX["bwd_bytes"])
_DURATION_COL = _IDX["flow_duration"]

TRUE_LABEL = "true_label"   # ground truth 0/1; the defender never sees this column


PER_FLOW_COLUMNS = ("duration_s", "packets", "bytes", "depth")   # column order of CostMetadata.per_flow
_FWD_PKT, _BWD_PKT = _IDX["fwd_packets"], _IDX["bwd_packets"]


def per_flow_cost(x: np.ndarray) -> np.ndarray:
    """(n, 4) attacker-cost record per flow: duration (s), packets, bytes, and
    protocol-state depth. Depth is the number of request/response exchanges the
    flow sustained — min(fwd, bwd) packets — the flow-level stand-in for what a
    honeypot log would report as commands executed / protocol state reached."""
    x = np.asarray(x, dtype="float64")
    return np.column_stack([
        x[:, _DURATION_COL] / 1e6,
        x[:, _PACKET_COLS].sum(axis=1),
        x[:, _BYTE_COLS].sum(axis=1),
        np.minimum(x[:, _FWD_PKT], x[:, _BWD_PKT]),
    ])


@dataclass(frozen=True)
class CostMetadata:
    """What a batch cost the attacker: batch totals, plus the per-flow record the
    totals were summed from (D1 weights individual samples by their own cost)."""

    flows: int
    packets: float
    bytes: float
    duration_s: float
    per_flow: np.ndarray | None = field(default=None, compare=False, repr=False)


def cost_metadata(x: np.ndarray) -> CostMetadata:
    x = np.asarray(x, dtype="float64")
    pf = per_flow_cost(x)
    return CostMetadata(
        flows=int(len(x)),
        packets=float(x[:, _PACKET_COLS].sum()),
        bytes=float(x[:, _BYTE_COLS].sum()),
        duration_s=float(x[:, _DURATION_COL].sum() / 1e6),
        per_flow=pf,
    )


def batch_frame(x: np.ndarray, true_label: int, *, resampled: bool) -> pd.DataFrame:
    """Canonical feature columns plus ``true_label``. ``attrs["resampled"]`` is
    set when the pool was exhausted and rows were reused."""
    df = pd.DataFrame(x, columns=list(schema.CANONICAL_FEATURES))
    df[TRUE_LABEL] = np.full(len(df), true_label, dtype="int64")
    df.attrs["resampled"] = bool(resampled)
    return df


def features_of(batch: pd.DataFrame) -> np.ndarray:
    return batch[list(schema.CANONICAL_FEATURES)].to_numpy("float64")


class Adversary(abc.ABC):
    """Draws fresh rows from a pool without replacement (the pool is disjoint
    from ``trusted_eval``), reshuffling and flagging ``resampled`` if a
    scenario needs more rows than the pool holds. The permutation depends only
    on ``seed``, so every arm/ratio/jitter sharing a seed sees nested batches."""

    def __init__(self, pool: np.ndarray, seed: int) -> None:
        self._pool = pool
        self._seed = seed
        self._rng = np.random.default_rng(seed)
        self._order = self._rng.permutation(len(pool))
        self._cursor = 0

    def _take(self, n: int) -> tuple[np.ndarray, bool]:
        resampled = False
        out = []
        while n > 0:
            if self._cursor >= len(self._order):
                self._order = self._rng.permutation(len(self._pool))
                self._cursor = 0
                resampled = True
            k = min(n, len(self._order) - self._cursor)
            out.append(self._order[self._cursor:self._cursor + k])
            self._cursor += k
            n -= k
        idx = np.concatenate(out) if out else np.empty(0, dtype=np.int64)
        return self._pool[idx].astype("float64"), resampled

    @abc.abstractmethod
    def generate_batch(self, round_idx: int, budget: int) -> tuple[pd.DataFrame, CostMetadata]:
        """``budget`` flows for round ``round_idx`` and what they cost the attacker."""
