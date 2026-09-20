"""Defense hook interface — the slot D1/D2 plug into.

The loop calls a hook between auto-labeling and accumulation. It sees the batch
(features and ground truth), the label the auto-labeler stamped, and the
attacker-cost record (:class:`~dloop.adversary.base.CostMetadata`, which is what
D1 prices influence by). It returns a per-row ``sample_weight``; a defense may
also return ``admit=False`` to quarantine the whole batch (D2). ``sample_weight``
is the single weight channel (:mod:`dloop.models`), so D1 needs nothing else.
Phase 0 ships only the no-op.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from dloop.adversary.base import CostMetadata


@dataclass(frozen=True)
class DefenseDecision:
    weights: np.ndarray   # (n,) per-row sample_weight, >= 0
    admit: bool = True    # False -> the whole batch is quarantined


class DefenseHook(Protocol):
    def apply(self, batch: pd.DataFrame, cost: CostMetadata,
              stamped_label: np.ndarray) -> DefenseDecision: ...


class NoOpDefense:
    """Admit everything at weight 1 — the undefended loop."""

    def apply(self, batch: pd.DataFrame, cost: CostMetadata,
              stamped_label: np.ndarray) -> DefenseDecision:
        return DefenseDecision(weights=np.ones(len(stamped_label)), admit=True)
