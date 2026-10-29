"""Lab replay adversary (Phase B, DECISIONS.md §32).

Unlike :class:`~dloop.adversary.mimicry.MimicryAdversary`, which *synthesises*
A1 poison by jittering benign feature vectors, this adversary replays the
honeypot_pool rows **unchanged** — the real mimic flows the lab captured and the
fixed CICFlowMeter extracted. Each round it emits a budgeted sample of those rows
with ``true_label = 0`` (they are genuinely benign traffic); the labeler stamps
them malicious under the auto-label policy (the A1 arm) or benign under the
ground-truth policy (the a1truth null arm). Cost comes from the rows themselves.

It is :class:`~dloop.adversary.clean.CleanAdversary` with the benign true label:
no feature-space perturbation, no fidelity knob — the fidelity is whatever the
real capture achieved (measured in B.1).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dloop.adversary.base import Adversary, CostMetadata, batch_frame, cost_metadata


class LabReplayAdversary(Adversary):
    def __init__(self, pool_benign: np.ndarray, seed: int) -> None:
        super().__init__(pool_benign, seed)

    def generate_batch(self, round_idx: int, budget: int) -> tuple[pd.DataFrame, CostMetadata]:
        x, resampled = self._take(budget)
        # true_label 0: these are real benign-shaped flows, labelled malicious only
        # by the honeypot policy (that is the A1 poison).
        return batch_frame(x, 0, resampled=resampled), cost_metadata(x)
