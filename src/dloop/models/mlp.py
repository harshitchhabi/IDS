"""Small supervised PyTorch MLP detector.

``sample_weight`` weights the per-sample BCE loss directly (``reduction="none"``
-> multiply -> mean), the same pattern as the autoencoder's weighted
reconstruction loss and for the same reason: a weighted sampler changes the
gradient's variance and the effective dataset size rather than each sample's
exact pull, and D1 needs the exact pull.

Full-batch gradient descent: fast at Phase 0 volumes and bit-reproducible,
which a mini-batch ``DataLoader`` would not be. No ``class_weight`` /
``pos_weight`` rebalancing — see the package docstring.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch import nn

from dloop.models.base import Model, ModelConfig

_DEFAULTS = dict(hidden=(32, 16), epochs=250, lr=1e-3, weight_decay=0.0)


class _MLP(nn.Module):
    def __init__(self, d_in: int, hidden: tuple[int, ...]) -> None:
        super().__init__()
        dims = [d_in, *hidden]
        layers: list[nn.Module] = []
        for a, b in zip(dims[:-1], dims[1:], strict=True):
            layers += [nn.Linear(a, b), nn.ReLU()]
        layers.append(nn.Linear(dims[-1], 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)  # logits


class MLPModel(Model):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        self.params = {**_DEFAULTS, **config.hyperparams}
        self.net_: _MLP | None = None

    # ---- training -----------------------------------------------------
    def _fit_impl(self, x: np.ndarray, y: np.ndarray, sample_weight: np.ndarray) -> None:
        xt = torch.tensor(x, dtype=torch.float32)
        yt = torch.tensor(y, dtype=torch.float32)
        wt = torch.tensor(sample_weight, dtype=torch.float32)
        wt = wt / wt.mean().clamp_min(1e-12)  # normalise so lr semantics are stable

        torch.manual_seed(self.config.seed)
        net = _MLP(xt.shape[1], tuple(self.params["hidden"]))
        opt = torch.optim.Adam(net.parameters(), lr=self.params["lr"],
                               weight_decay=self.params["weight_decay"])
        bce = nn.BCEWithLogitsLoss(reduction="none")

        net.train()
        for _ in range(int(self.params["epochs"])):
            opt.zero_grad()
            logits = net(xt)
            per_sample = bce(logits, yt)         # reduction="none"
            loss = (per_sample * wt).mean()       # true per-sample weights
            loss.backward()
            opt.step()

        net.eval()
        self.net_ = net

    # ---- scoring -----------------------------------------------------
    def _logits(self, x: np.ndarray) -> np.ndarray:
        assert self.net_ is not None
        with torch.no_grad():
            xt = torch.tensor(x, dtype=torch.float32)
            return self.net_(xt).numpy().astype("float64")

    def _score_impl(self, x: np.ndarray) -> np.ndarray:
        logits = self._logits(x)
        return 1.0 / (1.0 + np.exp(-logits))

    def _proba_impl(self, x: np.ndarray) -> np.ndarray:
        p_attack = self._score_impl(x)
        return np.column_stack([1.0 - p_attack, p_attack])

    # ---- persistence ----------------------------------------------
    def _save_estimator(self, path: Path) -> None:
        torch.save(
            {
                "state_dict": self.net_.state_dict(),
                "d_in": self.net_.net[0].in_features,
                "hidden": tuple(self.params["hidden"]),
            },
            path,
        )

    def _load_estimator(self, path: Path) -> None:
        blob = torch.load(path, weights_only=True)
        self.net_ = _MLP(blob["d_in"], tuple(blob["hidden"]))
        self.net_.load_state_dict(blob["state_dict"])
        self.net_.eval()
