"""Tabular autoencoder detector — unsupervised, trained on benign only.

Scores by reconstruction error: benign traffic reconstructs well, attacks do
not. ``sample_weight`` weights the per-sample reconstruction loss directly
(``reduction="none"`` -> multiply -> mean), which is what D1 needs; a weighted
sampler is *not* an acceptable substitute because it changes the gradient's
variance and the effective dataset size rather than each sample's exact pull.

Full-batch gradient descent on a small MLP: fast on Phase 0 volumes and
bit-reproducible, which a mini-batch ``DataLoader`` would not be.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch import nn

from dloop.models.base import Model, ModelConfig

_DEFAULTS = dict(hidden=(16, 8), epochs=250, lr=1e-3, weight_decay=0.0)


class _AE(nn.Module):
    def __init__(self, d_in: int, hidden: tuple[int, ...]) -> None:
        super().__init__()
        dims = [d_in, *hidden]
        enc: list[nn.Module] = []
        for a, b in zip(dims[:-1], dims[1:], strict=True):
            enc += [nn.Linear(a, b), nn.ReLU()]
        dec: list[nn.Module] = []
        rev = dims[::-1]
        for a, b in zip(rev[:-1], rev[1:], strict=True):
            dec += [nn.Linear(a, b), nn.ReLU()]
        dec = dec[:-1]  # linear output layer
        self.net = nn.Sequential(*enc, *dec)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class AutoencoderModel(Model):
    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        self.params = {**_DEFAULTS, **config.hyperparams}
        self.net_: _AE | None = None
        self.err_mean_: float = 0.0
        self.err_std_: float = 1.0

    # ---- training -----------------------------------------------------
    def _fit_impl(self, x: np.ndarray, y: np.ndarray, sample_weight: np.ndarray) -> None:
        benign = y == 0
        if benign.sum() < 10:
            raise ValueError("autoencoder needs benign rows to train on")
        xb = torch.tensor(x[benign], dtype=torch.float32)
        wb = torch.tensor(sample_weight[benign], dtype=torch.float32)
        wb = wb / wb.mean().clamp_min(1e-12)  # normalise so lr semantics are stable

        torch.manual_seed(self.config.seed)
        net = _AE(xb.shape[1], tuple(self.params["hidden"]))
        opt = torch.optim.Adam(net.parameters(), lr=self.params["lr"],
                               weight_decay=self.params["weight_decay"])

        net.train()
        for _ in range(int(self.params["epochs"])):
            opt.zero_grad()
            recon = net(xb)
            per_sample = ((recon - xb) ** 2).mean(dim=1)   # reduction="none"
            loss = (per_sample * wb).mean()                # true per-sample weights
            loss.backward()
            opt.step()

        net.eval()
        self.net_ = net
        with torch.no_grad():
            err = ((net(xb) - xb) ** 2).mean(dim=1).numpy()
        # standardise scores by the *weighted* benign-train error distribution
        w = sample_weight[benign].astype("float64")
        w = w / w.sum() if w.sum() > 0 else np.full(len(err), 1 / len(err))
        self.err_mean_ = float(np.sum(w * err))
        self.err_std_ = float(np.sqrt(np.sum(w * (err - self.err_mean_) ** 2)) or 1.0)

    # ---- scoring -----------------------------------------------------
    def _recon_err(self, x: np.ndarray) -> np.ndarray:
        assert self.net_ is not None
        with torch.no_grad():
            xt = torch.tensor(x, dtype=torch.float32)
            return ((self.net_(xt) - xt) ** 2).mean(dim=1).numpy().astype("float64")

    def _score_impl(self, x: np.ndarray) -> np.ndarray:
        return (self._recon_err(x) - self.err_mean_) / self.err_std_

    def _proba_impl(self, x: np.ndarray) -> np.ndarray:
        p_attack = 1.0 / (1.0 + np.exp(-self._score_impl(x)))
        return np.column_stack([1.0 - p_attack, p_attack])

    # ---- persistence ----------------------------------------------
    def _save_estimator(self, path: Path) -> None:
        torch.save(
            {
                "state_dict": self.net_.state_dict(),
                "d_in": self.net_.net[0].in_features,
                "hidden": tuple(self.params["hidden"]),
                "err_mean": self.err_mean_,
                "err_std": self.err_std_,
            },
            path,
        )

    def _load_estimator(self, path: Path) -> None:
        blob = torch.load(path, weights_only=True)
        self.net_ = _AE(blob["d_in"], tuple(blob["hidden"]))
        self.net_.load_state_dict(blob["state_dict"])
        self.net_.eval()
        self.err_mean_ = float(blob["err_mean"])
        self.err_std_ = float(blob["err_std"])
