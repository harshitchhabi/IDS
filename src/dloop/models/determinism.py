"""Deterministic seeding for every RNG the model layer touches.

CLAUDE.md: "Fixed seeds everywhere (numpy, sklearn, torch). Experiment results
must be reproducible bit-for-bit from a config." This module makes that literally
true rather than aspirational — call :func:`seed_everything` at the top of every
``fit``.
"""

from __future__ import annotations

import os
import random

import numpy as np

from dloop.logging_config import get_logger

log = get_logger("models.determinism")


def seed_everything(seed: int) -> None:
    """Seed Python, NumPy and (if installed) PyTorch, and force deterministic
    kernels. Idempotent; safe to call once per ``fit``."""
    os.environ["PYTHONHASHSEED"] = str(seed)
    # Needed for deterministic cuBLAS matmuls; harmless on CPU.
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    random.seed(seed)
    np.random.seed(seed)

    try:
        import torch
    except ImportError:  # pragma: no cover - torch is a hard dep, defensive only
        return

    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    # Single-threaded: multi-threaded reductions are not bit-reproducible.
    torch.set_num_threads(1)
