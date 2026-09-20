"""Loop configuration: how the defender retains honeypot data and how the
adversary's per-round budget is set. Both are config, not hardcoded.

``retention``
    ``accumulate`` (default) keeps every admitted honeypot batch forever, which
    is the literature's "continuous adaptation" design and the worst case for
    the defender: influence only grows. ``sliding_window`` keeps only the last
    ``window_rounds`` rounds of honeypot batches (seed_train is always kept), the
    obvious mitigation to test against slow poisoning.

``budget_mode``
    ``fixed_ratio`` sizes per-round batches so the honeypot share of the training
    set reaches ``poison_ratio`` by the final round (``accumulate``) or once the
    window is full (``sliding_window``). This is what damage curves use: every
    point on the curve has the same, known poison share. ``fixed_batch`` gives the
    adversary a constant ``batch_size`` flows per round regardless of ratio; the
    poison share then *evolves* (grows under ``accumulate``, plateaus under a
    window). This is what temporal-dynamics experiments use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Retention = Literal["accumulate", "sliding_window"]
BudgetMode = Literal["fixed_ratio", "fixed_batch"]


@dataclass(frozen=True)
class LoopConfig:
    rounds: int = 20
    retention: Retention = "accumulate"
    window_rounds: int | None = None
    budget_mode: BudgetMode = "fixed_ratio"
    poison_ratio: float = 0.0     # fixed_ratio only
    batch_size: int = 0           # fixed_batch only
    target_fpr: float = 0.01

    def __post_init__(self) -> None:
        if self.rounds < 1:
            raise ValueError("rounds must be >= 1")
        if self.retention == "sliding_window" and (self.window_rounds is None or self.window_rounds < 1):
            raise ValueError("sliding_window retention needs window_rounds >= 1")
        if self.retention == "accumulate" and self.window_rounds is not None:
            raise ValueError("window_rounds is only meaningful with retention='sliding_window'")
        if self.budget_mode == "fixed_ratio" and not (0.0 <= self.poison_ratio < 1.0):
            raise ValueError("poison_ratio must be in [0, 1)")
        if self.budget_mode == "fixed_batch" and self.batch_size < 0:
            raise ValueError("batch_size must be >= 0")

    def budgets(self, n_seed: int) -> list[int]:
        """Flows the adversary generates in rounds 1..``rounds``."""
        if self.budget_mode == "fixed_batch":
            return [int(self.batch_size)] * self.rounds
        if self.poison_ratio <= 0:
            return [0] * self.rounds
        total = self.poison_ratio / (1.0 - self.poison_ratio) * n_seed
        if self.retention == "accumulate":
            # cumulative rounding so the final cumulative count is exact
            cum = [int(round(total * k / self.rounds)) for k in range(self.rounds + 1)]
            return [cum[k] - cum[k - 1] for k in range(1, self.rounds + 1)]
        per_round = int(round(total / self.window_rounds))
        return [per_round] * self.rounds

    def tag(self) -> str:
        """Job-key suffix; empty for the default so earlier results keep their names."""
        if self.retention == "accumulate" and self.budget_mode == "fixed_ratio":
            return ""
        w = f"w{self.window_rounds}" if self.retention == "sliding_window" else "acc"
        b = f"b{self.batch_size}" if self.budget_mode == "fixed_batch" else "fr"
        return f"_{w}_{b}"
