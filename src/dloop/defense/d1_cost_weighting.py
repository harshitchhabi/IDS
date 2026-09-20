"""D1 — cost-of-influence weighting. Definition: DECISIONS.md §20 (fixed before
any D1 result). Poisoning through the honeypot is attractive only while it is
cheap, so make a sample's influence on the model purchasable with attacker effort.

For each honeypot flow with per-flow cost ``x = (duration_s, packets, bytes,
depth)``::

    e = prod_k (1 + x_k / r_k) ** alpha_k  -  1        effort, in "typical benign flows"
    w = min(1, (e / E_star) ** gamma)                   sample_weight

``r_k`` is the median of component ``k`` over the *benign rows of seed_train*
(trusted, defender-owned). ``e`` is 0 iff every component is 0, strictly increasing
in every component, and unit-free. The weight rides entirely on ``sample_weight``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dloop.adversary.base import PER_FLOW_COLUMNS, CostMetadata, per_flow_cost
from dloop.defense.base import DefenseDecision, TrainingView

COMPONENTS = PER_FLOW_COLUMNS   # ("duration_s", "packets", "bytes", "depth")
_FLOOR = 1e-9


@dataclass(frozen=True)
class D1Config:
    e_star: float = 8.0
    gamma: float = 2.0
    # weights over (duration, packets, bytes, depth); geometric-mean effort. Zero
    # drops a component (ablation); they are renormalized to sum to 1.
    alpha: tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25)

    def __post_init__(self) -> None:
        if self.e_star <= 0:
            raise ValueError("e_star must be > 0")
        if self.gamma < 1:
            raise ValueError("gamma must be >= 1")
        if len(self.alpha) != 4 or min(self.alpha) < 0 or sum(self.alpha) <= 0:
            raise ValueError("alpha must be four non-negative weights with a positive sum")

    @property
    def alpha_normalized(self) -> np.ndarray:
        a = np.asarray(self.alpha, dtype="float64")
        return a / a.sum()

    def tag(self) -> str:
        short = {"duration_s": "dur", "packets": "pkt", "bytes": "byt", "depth": "dep"}
        comp = "" if len(set(self.alpha)) == 1 else "_c" + "".join(
            short[n] for n, a in zip(COMPONENTS, self.alpha) if a > 0)
        return f"d1_E{self.e_star:g}_g{self.gamma:g}{comp}"


class CostFunction:
    def __init__(self, reference_per_flow: np.ndarray, config: D1Config) -> None:
        ref = np.asarray(reference_per_flow, dtype="float64")
        self.reference = np.maximum(np.median(ref, axis=0), _FLOOR)
        self.config = config

    def effort(self, per_flow: np.ndarray) -> np.ndarray:
        x = np.asarray(per_flow, dtype="float64")
        if (x < 0).any():
            raise ValueError("cost components must be non-negative")
        log_g = (np.log1p(x / self.reference) * self.config.alpha_normalized).sum(axis=1)
        return np.expm1(log_g)

    def weight(self, per_flow: np.ndarray) -> np.ndarray:
        e = self.effort(per_flow)
        return np.minimum(1.0, (e / self.config.e_star) ** self.config.gamma)


class D1CostWeighting:
    def __init__(self, seed_x: np.ndarray, seed_y: np.ndarray, config: D1Config | None = None) -> None:
        self.config = config or D1Config()
        self.name = self.config.tag()
        benign = np.asarray(seed_x)[np.asarray(seed_y) == 0]
        self.cost_function = CostFunction(per_flow_cost(benign), self.config)

    def apply(self, batch: pd.DataFrame, cost: CostMetadata, stamped_label: np.ndarray) -> DefenseDecision:
        if cost.per_flow is None:
            raise ValueError("D1 needs CostMetadata.per_flow")
        return DefenseDecision(weights=self.cost_function.weight(cost.per_flow), admit=True)

    def sanitize(self, view: TrainingView) -> np.ndarray:
        return view.w
