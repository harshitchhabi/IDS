"""S0 — the clean adversary: genuine attack flows reach the decoy.

Labels are correct, so the loop's auto-labeling policy ("everything the
honeypot sees is malicious") is right by construction. The detector must
improve here or nothing downstream means anything (CLAUDE.md, S0).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dloop.adversary.base import Adversary, CostMetadata, batch_frame, cost_metadata


class CleanAdversary(Adversary):
    def __init__(self, pool_attack: np.ndarray, seed: int) -> None:
        super().__init__(pool_attack, seed)

    def generate_batch(self, round_idx: int, budget: int) -> tuple[pd.DataFrame, CostMetadata]:
        x, resampled = self._take(budget)
        return batch_frame(x, 1, resampled=resampled), cost_metadata(x)
