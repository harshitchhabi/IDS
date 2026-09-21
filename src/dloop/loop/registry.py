"""Versioned model registry: every retrain is a version, persisted with its sidecar and a row in the store.

The detector service loads the *current* version from here rather than being handed a model object, so what
is scoring live traffic is always something that was registered (and can be inspected or rolled back).
"""

from __future__ import annotations

import time
from pathlib import Path

from dloop.models import Model, load_model
from dloop.store.sqlite import Store


class ModelRegistry:
    def __init__(self, root: str | Path, store: Store) -> None:
        self.root = Path(root)
        self.store = store
        self.root.mkdir(parents=True, exist_ok=True)
        self._next = 0

    def reset(self) -> None:
        """Forget every version (a demo reset). Files of old versions are overwritten as versions restart."""
        self.store.reset(("models",))
        self._next = 0

    def register(self, model: Model, *, scenario: str, defense: str, round_: int, threshold_fixed: float,
                 threshold_recal: float, metrics: dict) -> int:
        version = self._next
        self._next += 1
        path = self.root / f"v{version}.model"
        model.save(path)
        self.store.add_model(version=version, created=time.time(), path=str(path), scenario=scenario,
                             defense=defense, round_=round_, threshold_fixed=threshold_fixed,
                             threshold_recal=threshold_recal, metrics=metrics)
        return version

    def current(self) -> tuple[int, Model, dict] | None:
        """(version, model, registry row) of the newest version, loaded from disk."""
        row = self.store.latest_model()
        if row is None:
            return None
        return row["version"], load_model(row["path"]), row
