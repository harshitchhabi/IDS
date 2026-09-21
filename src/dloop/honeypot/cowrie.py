"""Cowrie telemetry: tail Cowrie's JSON log into per-session records with a live effort score.

This is *real* honeypot telemetry and is deliberately kept apart from the loop: Cowrie sessions are not
CICFlowMeter flows, so nothing here feeds the model (DECISIONS.md 25.4, CLAUDE.md). What it shows is the
session-level effort signal (auth attempts, commands, bytes, duration) that flow data cannot give D1.

Effort uses the same form as D1 (DECISIONS.md 20) with fixed unit references, i.e. ``e = prod_k (1 + x_k/r_k)^(1/4) - 1``,
because a fresh honeypot has no trusted benign sessions to take medians from (this is the ``D1fixed`` variant).
"""

from __future__ import annotations

import json
import threading
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from dloop.logging_config import get_logger
from dloop.store.sqlite import Store

log = get_logger("honeypot.cowrie")

DEFAULT_LOG = Path("data/cowrie/log/cowrie.json")
# unit references: 3 auth attempts, 3 commands, 200 bytes typed, 10 s of session
EFFORT_REFERENCE = {"logins": 3.0, "commands": 3.0, "bytes": 200.0, "duration": 10.0}
ACTIVE_WINDOW_S = 20.0


def session_effort(logins: float, commands: float, nbytes: float, duration: float) -> float:
    e = 1.0
    for x, r in ((logins, "logins"), (commands, "commands"), (nbytes, "bytes"), (duration, "duration")):
        e *= (1.0 + x / EFFORT_REFERENCE[r]) ** 0.25
    return e - 1.0


def _ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


class CowrieTailer:
    def __init__(self, store: Store | None = None, path: str | Path | None = None) -> None:
        self.store = store
        self.path = Path(path) if path else DEFAULT_LOG
        self.sessions: dict[str, dict] = {}
        self.creds: Counter[str] = Counter()
        self.cmds: Counter[str] = Counter()
        self.totals = {"logins": 0, "login_success": 0, "commands": 0}
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._pos = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="cowrie-tailer")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll()
            except Exception:
                log.exception("cowrie tail failed")
            time.sleep(0.5)

    def poll(self) -> int:
        """Read any new complete lines. Returns how many events were consumed."""
        if not self.path.exists():
            return 0
        size = self.path.stat().st_size
        if size < self._pos:          # log rotated / truncated
            self._pos = 0
        n = 0
        with self.path.open("rb") as f:
            f.seek(self._pos)
            while True:
                line = f.readline()
                if not line or not line.endswith(b"\n"):
                    break             # partial line: pick it up next poll
                self._pos = f.tell()
                try:
                    self.handle(json.loads(line))
                    n += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    log.warning("skipping malformed cowrie line", line=line[:120].decode("utf-8", "replace"))
        return n

    def handle(self, ev: dict) -> None:
        eid, sid = ev.get("eventid", ""), ev.get("session")
        if not sid:
            return
        t = _ts(ev["timestamp"]) if "timestamp" in ev else time.time()
        with self._lock:
            s = self.sessions.setdefault(sid, {"session": sid, "src_ip": ev.get("src_ip"), "started": t, "ended": None,
                                              "logins": 0, "commands": 0, "bytes": 0, "duration": 0.0,
                                              "effort": 0.0, "last": t})
            s["last"] = max(s["last"], t)
            if eid == "cowrie.session.connect":
                s["src_ip"], s["started"] = ev.get("src_ip"), t
            elif eid in ("cowrie.login.failed", "cowrie.login.success"):
                s["logins"] += 1
                self.totals["logins"] += 1
                self.totals["login_success"] += eid.endswith("success")
                self.creds[f"{ev.get('username', '')} / {ev.get('password', '')}"] += 1
                s["bytes"] += len(str(ev.get("username", ""))) + len(str(ev.get("password", "")))
            elif eid == "cowrie.command.input":
                cmd = str(ev.get("input", ""))
                s["commands"] += 1
                self.totals["commands"] += 1
                s["bytes"] += len(cmd)
                self.cmds[cmd] += 1
            elif eid == "cowrie.session.closed":
                s["ended"], s["duration"] = t, float(ev.get("duration", t - s["started"]))
            s["duration"] = s["duration"] if s["ended"] else max(s["duration"], t - s["started"])
            s["effort"] = session_effort(s["logins"], s["commands"], s["bytes"], s["duration"])
            snap = dict(s)
        if self.store is not None:
            self.store.upsert_session(snap)

    def snapshot(self) -> dict:
        now = time.time()
        with self._lock:
            sess = sorted(self.sessions.values(), key=lambda s: -s["last"])[:12]
            out = [{**s, "active": s["ended"] is None and now - s["last"] < ACTIVE_WINDOW_S} for s in sess]
            return {"enabled": self.path.exists() or bool(self.sessions),
                    "totals": {"sessions": len(self.sessions), "logins": self.totals["logins"],
                               "login_success": self.totals["login_success"], "commands": self.totals["commands"],
                               "distinct_credentials": len(self.creds)},
                    "sessions": out, "credentials": self.creds.most_common(8), "commands": self.cmds.most_common(8)}
