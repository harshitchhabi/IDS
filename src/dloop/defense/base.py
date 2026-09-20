"""Defense interface — the slots D1/D2 and the generic baselines plug into.

Two hook points, because two families of defense need different information:

* ``apply(batch, cost, stamped_label)`` runs once per honeypot batch, between
  auto-labeling and accumulation. It sees the batch, the attacker-cost record
  (:class:`~dloop.adversary.base.CostMetadata`, including per-flow costs — what D1
  prices influence by) and the stamped label, and returns per-row
  ``sample_weight`` plus an admit flag (D2 quarantines a whole batch).
* ``sanitize(view)`` runs at each retrain, over the whole accumulated training set
  (:class:`TrainingView`). Filters that need the data the model is about to be fit
  on — loss-based filtering — live here.

Both return weights: ``sample_weight`` is the single weight channel
(:mod:`dloop.models`); nothing else adjusts a sample's influence. A defense may
only change the weights of honeypot-derived rows; seed_train is trusted, and the
loop asserts it is untouched.
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


@dataclass(frozen=True)
class TrainingView:
    """The training set at a retrain. Rows ``[:n_seed]`` are trusted seed_train."""

    x: np.ndarray              # (n, F) raw canonical features
    y: np.ndarray              # (n,) stamped labels
    w: np.ndarray              # (n,) current weights
    is_honeypot: np.ndarray    # (n,) bool
    round_idx: int
    seed: int


class Defense(Protocol):
    name: str

    def apply(self, batch: pd.DataFrame, cost: CostMetadata,
              stamped_label: np.ndarray) -> DefenseDecision: ...

    def sanitize(self, view: TrainingView) -> np.ndarray: ...


class NoOpDefense:
    """Admit everything at weight 1 — the undefended loop."""

    name = "none"

    def apply(self, batch: pd.DataFrame, cost: CostMetadata,
              stamped_label: np.ndarray) -> DefenseDecision:
        return DefenseDecision(weights=np.ones(len(stamped_label)), admit=True)

    def sanitize(self, view: TrainingView) -> np.ndarray:
        return view.w
