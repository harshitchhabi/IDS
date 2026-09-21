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


# Generic fixed units (1 s, 10 packets, 1000 bytes, 3 exchanges): within a factor of ~2-3 of the
# benign medians of both datasets used here, and needing no trusted data (DECISIONS.md 24).
FIXED_REFERENCE = (1.0, 10.0, 1000.0, 3.0)


@dataclass(frozen=True)
class D1Config:
    e_star: float = 8.0
    gamma: float = 2.0
    # If set, E* is the q-quantile of the effort of the trusted benign rows (normalises the
    # benign *tail* per dataset) and ``e_star`` is ignored.
    e_star_quantile: float | None = None
    # "median": per-component reference = median over trusted benign rows (the pre-registered
    # form). "fixed": FIXED_REFERENCE, no trusted data needed.
    reference: str = "median"
    # weights over (duration, packets, bytes, depth); geometric-mean effort. Zero
    # drops a component (ablation); they are renormalized to sum to 1.
    alpha: tuple[float, float, float, float] = (0.25, 0.25, 0.25, 0.25)

    def __post_init__(self) -> None:
        if self.e_star <= 0:
            raise ValueError("e_star must be > 0")
        if self.e_star_quantile is not None and not (0.0 < self.e_star_quantile < 1.0):
            raise ValueError("e_star_quantile must be in (0, 1)")
        if self.reference not in ("median", "fixed"):
            raise ValueError("reference must be 'median' or 'fixed'")
        if self.reference == "fixed" and self.e_star_quantile is not None:
            raise ValueError("a quantile E* needs trusted benign rows; use reference='median'")
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
        head = (f"d1q_q{self.e_star_quantile:g}" if self.e_star_quantile is not None
                else f"d1fixed_E{self.e_star:g}" if self.reference == "fixed"
                else f"d1_E{self.e_star:g}")
        return f"{head}_g{self.gamma:g}{comp}"


class CostFunction:
    def __init__(self, reference_per_flow: np.ndarray | None, config: D1Config) -> None:
        """``reference_per_flow``: per-flow cost rows of the trusted benign flows (unused for
        ``reference='fixed'``, where no trusted data is needed)."""
        self.config = config
        if config.reference == "fixed":
            self.reference = np.asarray(FIXED_REFERENCE, dtype="float64")
        else:
            ref = np.asarray(reference_per_flow, dtype="float64")
            self.reference = np.maximum(np.median(ref, axis=0), _FLOOR)
        self.e_star = config.e_star
        if config.e_star_quantile is not None:
            self.e_star = float(np.quantile(self.effort(np.asarray(reference_per_flow, dtype="float64")),
                                            config.e_star_quantile))
            if self.e_star <= 0:
                raise ValueError("quantile E* is not positive: benign effort is degenerate")

    def effort(self, per_flow: np.ndarray) -> np.ndarray:
        x = np.asarray(per_flow, dtype="float64")
        if (x < 0).any():
            raise ValueError("cost components must be non-negative")
        log_g = (np.log1p(x / self.reference) * self.config.alpha_normalized).sum(axis=1)
        return np.expm1(log_g)

    def weight(self, per_flow: np.ndarray) -> np.ndarray:
        e = self.effort(per_flow)
        return np.minimum(1.0, (e / self.e_star) ** self.config.gamma)


class D1CostWeighting:
    def __init__(self, seed_x: np.ndarray, seed_y: np.ndarray, config: D1Config | None = None) -> None:
        self.config = config or D1Config()
        self.name = self.config.tag()
        benign = np.asarray(seed_x)[np.asarray(seed_y) == 0]
        self.cost_function = CostFunction(per_flow_cost(benign), self.config)
        self.e_star_effective = self.cost_function.e_star

    def apply(self, batch: pd.DataFrame, cost: CostMetadata, stamped_label: np.ndarray) -> DefenseDecision:
        if cost.per_flow is None:
            raise ValueError("D1 needs CostMetadata.per_flow")
        return DefenseDecision(weights=self.cost_function.weight(cost.per_flow), admit=True)

    def sanitize(self, view: TrainingView) -> np.ndarray:
        return view.w
