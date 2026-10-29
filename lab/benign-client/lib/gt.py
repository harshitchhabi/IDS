"""Ground-truth logging shared by benign-client and attacker. One JSON line per
session: who talked to whom, on what port, and the TRUE intent. tools/label.py
joins these against the extracted flows, so the fields here are the join key."""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path

_LOCK = threading.Lock()


def own_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("172.28.0.1", 9))  # no packet sent for UDP connect; just resolves src
        return s.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        s.close()


class GroundTruth:
    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.src = own_ip()

    def log(self, *, dst: str, dst_port: int, intent: str, kind: str,
            t_start: float, t_end: float, **meta: object) -> None:
        rec = {"ts": t_start, "t_start": t_start, "t_end": t_end,
               "src": self.src, "dst": dst, "dst_port": int(dst_port),
               "intent": intent, "kind": kind, **meta}
        line = json.dumps(rec)
        with _LOCK, self.path.open("a") as fh:
            fh.write(line + "\n")
