"""SQLite store for the demo: alerts, model registry rows, loop rounds, honeypot sessions.

SQLite because CLAUDE.md says so (inspectable, zero setup). One connection guarded by a lock, since the
replay thread, the retrain thread and the API all write. ``check_same_thread=False`` is safe under that lock.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, family TEXT NOT NULL,
    predicted TEXT NOT NULL, score REAL NOT NULL, true_label INTEGER NOT NULL,
    injected INTEGER NOT NULL, model_version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS models (
    version INTEGER PRIMARY KEY, created REAL NOT NULL, path TEXT NOT NULL, scenario TEXT NOT NULL,
    defense TEXT NOT NULL, round INTEGER NOT NULL, threshold_fixed REAL NOT NULL,
    threshold_recal REAL NOT NULL, metrics TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS honeypot_sessions (
    session TEXT PRIMARY KEY, src_ip TEXT, started REAL, ended REAL, logins INTEGER, commands INTEGER,
    bytes INTEGER, duration REAL, effort REAL, data TEXT);
"""


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def reset(self, tables: Iterable[str] = ("alerts", "models")) -> None:
        with self._lock:
            for t in tables:
                self._db.execute(f"DELETE FROM {t}")
            self._db.commit()

    def add_alerts(self, rows: list[tuple]) -> None:
        """rows: (ts, family, predicted, score, true_label, injected, model_version)."""
        if not rows:
            return
        with self._lock:
            self._db.executemany(
                "INSERT INTO alerts (ts,family,predicted,score,true_label,injected,model_version) "
                "VALUES (?,?,?,?,?,?,?)", rows)
            self._db.commit()

    def alert_count(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0])

    def recent_alerts(self, n: int = 50) -> list[dict]:
        with self._lock:
            cur = self._db.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (n,))
            return [dict(r) for r in cur.fetchall()]

    def add_model(self, *, version: int, created: float, path: str, scenario: str, defense: str, round_: int,
                  threshold_fixed: float, threshold_recal: float, metrics: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO models VALUES (?,?,?,?,?,?,?,?,?)",
                (version, created, path, scenario, defense, round_, threshold_fixed, threshold_recal,
                 json.dumps(metrics)))
            self._db.commit()

    def models(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM models ORDER BY version").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["metrics"] = json.loads(d["metrics"])
            out.append(d)
        return out

    def latest_model(self) -> dict | None:
        with self._lock:
            r = self._db.execute("SELECT * FROM models ORDER BY version DESC LIMIT 1").fetchone()
        if r is None:
            return None
        d = dict(r)
        d["metrics"] = json.loads(d["metrics"])
        return d

    def upsert_session(self, s: dict) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO honeypot_sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (s["session"], s.get("src_ip"), s.get("started"), s.get("ended"), s.get("logins", 0),
                 s.get("commands", 0), s.get("bytes", 0), s.get("duration", 0.0), s.get("effort", 0.0),
                 json.dumps({k: v for k, v in s.items() if k not in ("session",)})))
            self._db.commit()
