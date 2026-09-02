"""Detection models behind one interface.

THE SINGLE WEIGHT CHANNEL — do not remove this rule.
====================================================
No model in this package may use ``class_weight="balanced"``, XGBoost's
``scale_pos_weight`` auto-heuristics, a weighted/oversampling ``DataLoader``,
SMOTE, or any other automatic class rebalancing.

Reason: the A1 attack works by injecting large volumes of malicious-labeled
samples into training. That shifts the class balance. Any automatic class
weighting would then shift in response, and the attack's measured effect on the
detector would be entangled with a rebalancing artifact — unattributable. The
paper's headline numbers depend on the effect being clean.

``sample_weight`` is the ONLY channel by which any sample's influence on the fit
is adjusted. D1 (cost-of-influence weighting) rides entirely on it. For the
PyTorch autoencoder, weighting is implemented as ``reduction="none"`` on the
loss, multiplied by the weight vector, then meaned — never approximated with a
weighted sampler, whose semantics differ.

LSTM is intentionally absent until S0/A1 are validated (sequence construction
over flow records is its own design problem).
"""

import json
from pathlib import Path

from dloop.models.autoencoder import AutoencoderModel
from dloop.models.base import Model, ModelConfig, ModelMetadata
from dloop.models.rf import RandomForestModel
from dloop.models.xgb import XGBoostModel

MODELS: dict[str, type[Model]] = {
    "rf": RandomForestModel,
    "xgboost": XGBoostModel,
    "autoencoder": AutoencoderModel,
}


def make_model(config: ModelConfig) -> Model:
    return MODELS[config.kind](config)


def load_model(path: str | Path) -> Model:
    """Load any saved model, dispatching on the ``kind`` in its sidecar."""
    p = Path(path)
    meta = json.loads(p.with_suffix(p.suffix + ".meta.json").read_text())
    return MODELS[meta["kind"]].load(p)


__all__ = [
    "Model", "ModelConfig", "ModelMetadata", "MODELS", "make_model", "load_model",
    "RandomForestModel", "XGBoostModel", "AutoencoderModel",
]
