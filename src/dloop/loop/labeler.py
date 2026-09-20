"""The auto-labeling policy — public, and the whole attack surface.

"Everything the honeypot sees is malicious." The policy never looks at the
features: that is precisely why an adversary who controls what the decoy sees
controls the labels (CLAUDE.md, threat model).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def auto_label(batch: pd.DataFrame) -> np.ndarray:
    return np.ones(len(batch), dtype=np.int64)
