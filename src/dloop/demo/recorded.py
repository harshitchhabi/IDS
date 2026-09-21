"""Recorded mode: precomputed trajectories of the real loop, replayed with the same interface as ``LiveLoop``.

``record_story`` runs the real :class:`~dloop.loop.live.LiveLoop` through the canonical story (S0, then A1, then
each defense switched on against the poisoned state, with A1 still arriving) and stores every round's row.
``RecordedLoop`` then serves those rows when the demo cannot train live (RAM pressure, a broken dependency).
Rows are the loop's own, so recorded mode shows the same numbers as live mode, not a mock-up.

Playback rules: S0 / A1 rounds walk the canonical path; with a defense on while the path is inside the A1 phase,
rounds come from that defense's recorded branch, counted from the round it was switched on. Past the end of a
recorded segment the last row is repeated and flagged ``recorded_clamped`` (never invented).
"""

from __future__ import annotations

import json
from pathlib import Path

from dloop.loop.live import DEFENSES, LiveLoop
from dloop.loop.registry import ModelRegistry

S0_ROUNDS, A1_ROUNDS, BRANCH_ROUNDS = 6, 12, 8


def record_story(loop: LiveLoop, out: str | Path, *, s0_rounds: int = S0_ROUNDS, a1_rounds: int = A1_ROUNDS,
                 branch_rounds: int = BRANCH_ROUNDS) -> dict:
    """Run the story on a real loop and write it. Branches restart from the poisoned state by replaying the same
    deterministic batches (the loop is seeded), so each defense sees exactly the same poison."""
    def run(defense_key: str) -> list[dict]:
        loop.reset()
        for _ in range(s0_rounds):
            loop.step("s0", "off")
        for _ in range(a1_rounds):
            loop.step("a1", "off")
        return [loop.step("a1", defense_key) for _ in range(branch_rounds)]

    run("off")
    canonical = list(loop.history)
    data = {"meta": {"model": loop.model_kind, "seed": loop.seed, "batch_size": loop.batch_size,
                     "s0_rounds": s0_rounds, "a1_rounds": a1_rounds, "branch_rounds": branch_rounds},
            "canonical": canonical, "branches": {}}
    for d in DEFENSES:
        if d == "off":
            continue
        data["branches"][d] = run(d)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(data))
    return data


class RecordedLoop:
    """Same surface as LiveLoop (``reset``, ``step``, ``history``, ``round``, ``batch_size``) with no ML."""

    model_kind = "recorded"
    recorded = True

    def __init__(self, path: str | Path, registry: ModelRegistry) -> None:
        self.data = json.loads(Path(path).read_text())
        self.registry = registry
        self.batch_size = self.data["meta"]["batch_size"]
        self.seed = self.data["meta"]["seed"]
        self.reset()

    def reset(self) -> None:
        self.registry.reset()
        self.history: list[dict] = []
        self.round = -1
        self.pos = 0                     # canonical rows consumed (row 0 = the seed-only model)
        self._defense_key = "off"
        self._since = 0
        self._emit(self.data["canonical"][0], "none", "off", clamped=False)

    def _emit(self, src: dict, scenario: str, defense_key: str, clamped: bool) -> dict:
        self.round += 1
        row = dict(src) | {"round": self.round, "scenario": scenario, "defense_key": defense_key,
                           "recorded_clamped": clamped}
        row["version"] = self.registry._next
        self.registry._next += 1
        self.registry.store.add_model(version=row["version"], created=0.0, path="", scenario=scenario,
                                      defense=defense_key, round_=self.round,
                                      threshold_fixed=row["modes"]["fixed"]["threshold"],
                                      threshold_recal=row["modes"]["recalibrated"]["threshold"], metrics=row)
        self.history.append(row)
        return row

    def step(self, scenario: str, defense_name: str) -> dict:
        canon = self.data["canonical"]
        s0n = self.data["meta"]["s0_rounds"]
        clamped = False
        if scenario == "s0" and self.pos < s0n:
            self.pos += 1
        elif scenario == "a1":
            self.pos = max(self.pos, s0n) + 1
            if self.pos >= len(canon):
                self.pos, clamped = len(canon) - 1, True
        elif scenario == "s0":
            clamped = True
        if defense_name != self._defense_key:
            self._defense_key, self._since = defense_name, 0
        src = canon[self.pos]
        if defense_name != "off" and self.pos > s0n:
            branch = self.data["branches"][defense_name]
            k = min(self._since, len(branch) - 1)
            clamped = clamped or self._since >= len(branch)
            src = branch[k]
            self._since += 1
        return self._emit(src, scenario, defense_name, clamped)
