"""The demo service: replay driver + detector + loop controller, exposed as a JSON snapshot for the dashboard.

Everything runs in one asyncio process. The 10 Hz stream tick scores flows with the model the registry says is
current; loop rounds (real retrains, ~0.5 s) run in a worker thread on a timer so scoring never stalls; the
dashboard gets a snapshot over a WebSocket twice a second.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Callable

import numpy as np

from dloop.demo.replay import BURST_FAMILIES, BURST_SIZE, ReplayDriver
from dloop.logging_config import get_logger
from dloop.loop.live import DEFENSES

log = get_logger("demo.service")

TICK_S = 0.1
PUSH_S = 0.5
ROUND_INTERVAL_S = 3.0
WINDOW_FLOWS = 1500     # rolling window for live FPR / TPR
BUCKETS = 90            # seconds of traffic history kept


class DemoService:
    def __init__(self, *, loop, registry, detector, driver: ReplayDriver | None, store, honeypot=None,
                 recorded: bool = False) -> None:
        self.loop, self.registry, self.detector, self.driver = loop, registry, detector, driver
        self.store, self.honeypot, self.recorded = store, honeypot, recorded
        self.feed = "off"                    # s0 | a1 | off
        self.defense = "off"
        self.auto = True
        self.interval = ROUND_INTERVAL_S
        self.busy = False
        self._last_round_t = 0.0
        self._pending_round = False
        self._buckets: deque[dict] = deque(maxlen=BUCKETS)
        self._window: deque[tuple[bool, bool]] = deque(maxlen=WINDOW_FLOWS)   # (is_attack, alerted)
        self._alerts: deque[dict] = deque(maxlen=60)
        self._new_alerts: list[dict] = []
        self.class_stats: dict[str, list[int]] = {}      # family -> [flows, alerted]
        self.total_flows = 0
        self.total_alerts = 0
        self._tasks: list[asyncio.Task] = []
        self.subscribers: set[Callable[[dict], Any]] = set()

    # ---- lifecycle --------------------------------------------------
    async def start(self) -> None:
        self._tasks = [asyncio.create_task(self._stream_loop()), asyncio.create_task(self._round_loop()),
                       asyncio.create_task(self._push_loop())]
        if self.honeypot is not None:
            self.honeypot.start()

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        if self.honeypot is not None:
            self.honeypot.stop()

    # ---- controls ---------------------------------------------------
    def set_feed(self, feed: str) -> None:
        if feed not in ("s0", "a1", "off"):
            raise ValueError(feed)
        self.feed = feed
        if feed != "off":
            self._pending_round = True     # start feeding immediately rather than after the next timer

    def set_defense(self, defense: str) -> None:
        if defense not in DEFENSES:
            raise ValueError(defense)
        self.defense = defense
        self._pending_round = True         # show the effect on the next round, not in three seconds

    def step_once(self) -> None:
        self._pending_round = True

    def set_mode(self, mode: str) -> None:
        self.detector.set_mode(mode)

    def launch_attack(self, family: str, n: int = BURST_SIZE) -> int:
        if self.driver is None:
            raise RuntimeError("no replay driver")
        return self.driver.launch(family, n)

    async def reset(self) -> None:
        while self.busy:
            await asyncio.sleep(0.05)
        self.busy = True
        try:
            await asyncio.get_running_loop().run_in_executor(None, self.loop.reset)
        finally:
            self.busy = False
        self.feed, self.defense = "off", "off"
        self._window.clear()
        self._alerts.clear()
        self._new_alerts.clear()
        self.class_stats.clear()
        self.total_flows = self.total_alerts = 0
        self._buckets.clear()
        self.store.reset(("alerts",))
        self.detector.refresh()

    # ---- tasks ------------------------------------------------------
    async def _stream_loop(self) -> None:
        last = time.monotonic()
        while True:
            await asyncio.sleep(TICK_S)
            now = time.monotonic()
            dt, last = now - last, now
            try:
                self.detector.refresh()
                x, fam, inj = self.driver.next_tick(dt) if self.driver else (None, np.empty(0), np.empty(0))
                scores, alerted = self.detector.score(x, fam)
                self._account(fam, inj, scores, alerted)
            except Exception:
                log.exception("stream tick failed")

    def _account(self, fam: np.ndarray, inj: np.ndarray, scores: np.ndarray, alerted: np.ndarray) -> None:
        if len(fam) == 0:
            return
        ts = time.time()
        sec = int(ts)
        if not self._buckets or self._buckets[-1]["t"] != sec:
            self._buckets.append({"t": sec, "benign": 0, "attack": 0, "alerts": 0})
        b = self._buckets[-1]
        is_atk = fam != "BENIGN"
        b["benign"] += int((~is_atk).sum())
        b["attack"] += int(is_atk.sum())
        b["alerts"] += int(alerted.sum())
        self.total_flows += len(fam)
        self.total_alerts += int(alerted.sum())
        for f in np.unique(fam):
            m = fam == f
            s = self.class_stats.setdefault(str(f), [0, 0])
            s[0] += int(m.sum())
            s[1] += int((alerted & m).sum())
        self._window.extend(zip(is_atk.tolist(), alerted.tolist()))
        rows = []
        v = self.detector.version
        for i in np.flatnonzero(alerted):
            rows.append((ts, str(fam[i]), "malicious", float(scores[i]), int(is_atk[i]), int(inj[i]), v))
        self.store.add_alerts(rows)
        for r in rows[-8:]:
            a = {"ts": r[0], "family": r[1], "predicted": r[2], "score": round(r[3], 3), "true_attack": bool(r[4]),
                 "injected": bool(r[5]), "version": r[6]}
            self._alerts.appendleft(a)
            self._new_alerts.append(a)

    async def _round_loop(self) -> None:
        while True:
            await asyncio.sleep(0.1)
            due = self.auto and self.feed != "off" and time.monotonic() - self._last_round_t >= self.interval
            if (due or self._pending_round) and not self.busy:
                self._pending_round = False
                self.busy = True
                scenario, defense = self.feed, self.defense
                try:
                    await asyncio.get_running_loop().run_in_executor(None, self.loop.step, scenario, defense)
                    self.detector.refresh()
                except Exception:
                    log.exception("loop round failed")
                finally:
                    self.busy = False
                    self._last_round_t = time.monotonic()

    async def _push_loop(self) -> None:
        while True:
            await asyncio.sleep(PUSH_S)
            if not self.subscribers:
                continue
            snap = self.snapshot()
            for cb in list(self.subscribers):
                try:
                    await cb(snap)
                except Exception:
                    self.subscribers.discard(cb)

    # ---- snapshot ---------------------------------------------------
    def _live_rates(self) -> dict:
        w = list(self._window)
        ben = [a for atk, a in w if not atk]
        atk = [a for atk_, a in w if atk_]
        return {"fpr": (sum(ben) / len(ben)) if ben else None, "tpr": (sum(atk) / len(atk)) if atk else None,
                "n_benign": len(ben), "n_attack": len(atk)}

    def defense_table(self) -> list[dict]:
        rows: dict[str, dict] = {}
        for h in self.loop.history:
            if h["n_honeypot"] == 0:
                continue
            d = rows.setdefault(h["defense_key"], {"defense": h["defense_key"], "rounds": 0, "sec": 0.0})
            d["rounds"] += 1
            d["sec"] += h["defense_seconds"]
            d.update(last_fpr=h["fixed_fpr"], last_tpr=h["fixed_tpr"], last_recal_tpr=h["recal_tpr"],
                     last_eff=h["hp_effective_ratio"])
        out = []
        for k in DEFENSES:
            if k in rows:
                d = rows[k]
                d["ms_per_round"] = 1000 * d.pop("sec") / d["rounds"]
                out.append(d)
        return out

    def rounds_summary(self) -> list[dict]:
        keys = ("round", "version", "scenario", "defense_key", "poison_ratio", "hp_effective_ratio", "fixed_fpr",
                "fixed_tpr", "recal_fpr", "recal_tpr", "defense_seconds", "fit_seconds", "n_honeypot", "s0_rows",
                "a1_rows")
        return [{k: h.get(k) for k in keys} for h in self.loop.history]

    def snapshot(self) -> dict:
        new, self._new_alerts = self._new_alerts, []
        cur = self._buckets[-2] if len(self._buckets) > 1 else (self._buckets[-1] if self._buckets else None)
        return {
            "t": time.time(),
            "recorded": self.recorded,
            "traffic": [{"t": b["t"], "benign": b["benign"], "attack": b["attack"], "alerts": b["alerts"]}
                        for b in self._buckets],
            "rate_now": (cur["benign"] + cur["attack"]) if cur else 0,
            "new_alerts": new[-30:],
            "alerts": list(self._alerts)[:14],
            "classes": {f: {"flows": v[0], "alerted": v[1]} for f, v in sorted(self.class_stats.items())},
            "live": self._live_rates(),
            "totals": {"flows": self.total_flows, "alerts": self.total_alerts},
            "detector": {"version": self.detector.version, "mode": self.detector.mode,
                         "threshold": self.detector.threshold if self.detector.version >= 0 else None},
            "control": {"feed": self.feed, "defense": self.defense, "busy": self.busy, "auto": self.auto,
                        "interval": self.interval, "round": self.loop.round,
                        "rate": self.driver.rate if self.driver else 0,
                        "burst_backlog": self.driver.burst_backlog if self.driver else 0,
                        "burst_families": list(BURST_FAMILIES)},
            "rounds": self.rounds_summary(),
            "defenses": self.defense_table(),
            "models": [{"version": m["version"], "scenario": m["scenario"], "defense": m["defense"],
                        "round": m["round"], "created": m["created"],
                        "fixed_fpr": m["metrics"]["fixed_fpr"], "fixed_tpr": m["metrics"]["fixed_tpr"],
                        "recal_fpr": m["metrics"]["recal_fpr"], "recal_tpr": m["metrics"]["recal_tpr"],
                        "poison": m["metrics"]["poison_ratio"], "eff": m["metrics"]["hp_effective_ratio"]}
                       for m in self.store.models()],
            "honeypot": self.honeypot.snapshot() if self.honeypot is not None else {"enabled": False},
        }
