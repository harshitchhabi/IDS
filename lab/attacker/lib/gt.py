"""Same ground-truth logger the benign client uses (copied so the attacker image
does not depend on the benign-client build context). See benign-client/lib/gt.py."""
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
        s.connect(("172.28.0.1", 9))
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
        with _LOCK, self.path.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
