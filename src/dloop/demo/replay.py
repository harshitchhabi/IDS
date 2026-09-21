"""Replay driver: streams CICIDS2017 flows at an adjustable, accelerated rate so it looks like live traffic.

The stream is mostly benign with a small ambient share of attacks (so per-class detection and TPR are always
measurable), and an operator can *launch an attack burst* of one family. A burst is emitted on top of the
ambient rate (a real burst raises the traffic rate) so it is visible on the dashboard within a second or two.

The rows come from ``trusted_eval``: they are scored, never trained on, so streaming them cannot leak into the
loop. (The loop's own training data lives in seed_train / honeypot_pool, which are disjoint from trusted_eval.)
"""

from __future__ import annotations

import numpy as np

RATE_MIN, RATE_MAX, RATE_DEFAULT = 50, 200, 100
BURST_FAMILIES = ("DDoS", "PortScan", "SSH-Patator")
MIN_FAMILY_ROWS = 50            # rarer families (Heartbleed, Infiltration, ...) are not streamed
AMBIENT_ATTACK_SHARE = 0.03
BURST_SIZE = 500
BURST_TICK_MULTIPLE = 2         # a burst adds up to 2x the base per-tick flow count on top of ambient traffic


class ReplayDriver:
    def __init__(self, benign_x: np.ndarray, attack_x: np.ndarray, attack_family: np.ndarray, *, seed: int = 0,
                 rate: float = RATE_DEFAULT) -> None:
        self._rng = np.random.default_rng(seed)
        self.benign_x = benign_x
        fams, counts = np.unique(attack_family, return_counts=True)
        self.families = [str(f) for f, c in zip(fams, counts) if c >= MIN_FAMILY_ROWS]
        self._by_family = {f: attack_x[attack_family == f] for f in self.families}
        self.rate = float(np.clip(rate, RATE_MIN, RATE_MAX))
        self._carry = 0.0
        self._burst: list[tuple[str, int]] = []   # (family, flows still to send)
        self.launched = 0

    def set_rate(self, rate: float) -> float:
        self.rate = float(np.clip(rate, RATE_MIN, RATE_MAX))
        return self.rate

    def launch(self, family: str, n: int = BURST_SIZE) -> int:
        if family not in self._by_family:
            raise ValueError(f"cannot launch {family!r}; available: {sorted(self._by_family)}")
        self._burst.append((family, int(n)))
        self.launched += int(n)
        return int(n)

    @property
    def burst_backlog(self) -> int:
        return sum(n for _, n in self._burst)

    def _sample(self, family: str, n: int) -> np.ndarray:
        pool = self._by_family[family]
        return pool[self._rng.integers(0, len(pool), n)]

    def next_tick(self, dt: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Flows for the last ``dt`` seconds: (x, family, injected). Family is ``BENIGN`` for benign flows."""
        self._carry += self.rate * dt
        n = int(self._carry)
        self._carry -= n
        xs: list[np.ndarray] = []
        fam: list[np.ndarray] = []
        inj: list[np.ndarray] = []
        n_atk = int(self._rng.binomial(n, AMBIENT_ATTACK_SHARE)) if n else 0
        if n - n_atk:
            xs.append(self.benign_x[self._rng.integers(0, len(self.benign_x), n - n_atk)])
            fam.append(np.full(n - n_atk, "BENIGN", dtype="U40"))
            inj.append(np.zeros(n - n_atk, dtype=bool))
        if n_atk:
            picked = self._rng.choice(self.families, n_atk)
            for f in np.unique(picked):
                k = int((picked == f).sum())
                xs.append(self._sample(str(f), k))
                fam.append(np.full(k, f, dtype="U40"))
                inj.append(np.zeros(k, dtype=bool))
        budget = int(BURST_TICK_MULTIPLE * max(n, 1))
        while self._burst and budget > 0:
            f, left = self._burst[0]
            k = min(left, budget)
            xs.append(self._sample(f, k))
            fam.append(np.full(k, f, dtype="U40"))
            inj.append(np.ones(k, dtype=bool))
            budget -= k
            if k == left:
                self._burst.pop(0)
            else:
                self._burst[0] = (f, left - k)
        if not xs:
            return (np.empty((0, self.benign_x.shape[1])), np.empty(0, dtype="U40"), np.empty(0, dtype=bool))
        order = self._rng.permutation(sum(len(a) for a in fam))
        return np.concatenate(xs)[order], np.concatenate(fam)[order], np.concatenate(inj)[order]
