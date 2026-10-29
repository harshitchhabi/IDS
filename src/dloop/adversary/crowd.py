"""Crowd-out: an adaptive attacker against a share cap (Phase R item R2, DECISIONS.md §31).

ShareCap weights every honeypot row by the same factor so the honeypot's
effective share of the training set stays at ``c``. That makes the honest decoy
traffic and anything else the honeypot logs compete for one fixed budget. This
attacker does not try to poison the boundary; it fills the honeypot with
benign-like filler so the genuine attack traffic the decoy also sees gets a
smaller slice of the capped share. Success is measured as lost S0 detection
gain, not as damage.

Each round's batch is the genuine batch (``genuine``, e.g. :class:`CleanAdversary`
over real attack rows, sized by the loop's budget) followed by
``round(factor * budget)`` filler rows from ``filler``. ``true_label`` is kept per
row; the auto-labeler stamps every row malicious regardless.

Two fillers (DECISIONS.md §31.6). The primary one, :class:`StaleReplayAdversary`,
replays correctly labelled attack rows the detector already trained on: volume
with no label conflict and no new information, so lost S0 gain under a cap is
dilution alone. The secondary one is A1's mimicry generator at jitter 0.7, benign
rows stamped malicious; it carries a label conflict of its own (s26.6).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dloop.adversary.base import Adversary, CostMetadata, cost_metadata, features_of, TRUE_LABEL
from dloop.adversary.clean import CleanAdversary


class StaleReplayAdversary(CleanAdversary):
    """Replays rows of one attack family taken from seed_train (``LoopData.
    seed_family_rows``): true label 1, which is also the stamp, so there is no label
    conflict, and every row is already in the training set. Draws without replacement
    and reshuffles (flagging ``resampled``) once the family's rows run out, which at
    large factors is the expected case for a replay."""


class CrowdOutAdversary:
    def __init__(self, genuine: Adversary, filler: Adversary, factor: float) -> None:
        if factor < 0:
            raise ValueError("factor must be >= 0")
        self.genuine, self.filler, self.factor = genuine, filler, float(factor)

    def generate_batch(self, round_idx: int, budget: int) -> tuple[pd.DataFrame, CostMetadata]:
        g, _ = self.genuine.generate_batch(round_idx, budget)
        n_fill = int(round(self.factor * budget))
        if n_fill == 0:
            return g, cost_metadata(features_of(g))
        f, _ = self.filler.generate_batch(round_idx, n_fill)
        f.columns = g.columns   # both are positional/canonical frames of one width
        batch = pd.concat([g, f], ignore_index=True)
        batch.attrs["resampled"] = bool(g.attrs.get("resampled") or f.attrs.get("resampled"))
        batch.attrs["n_genuine"] = len(g)
        batch[TRUE_LABEL] = batch[TRUE_LABEL].astype("int64")
        return batch, cost_metadata(features_of(batch))

    @staticmethod
    def genuine_mask(batch: pd.DataFrame) -> np.ndarray:
        n = int(batch.attrs.get("n_genuine", len(batch)))
        return np.arange(len(batch)) < n
