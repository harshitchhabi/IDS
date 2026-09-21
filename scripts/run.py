"""One entry point for the demo (no make on Windows).

    python scripts/run.py demo              # live: real loop, real retrains, dashboard on http://127.0.0.1:8000
    python scripts/run.py demo --recorded   # demo-day fallback: replays precomputed loop rounds, no training
    python scripts/run.py record            # (re)generate the recorded trajectories from the real loop
    python scripts/run.py test              # the test suite
    python scripts/run.py cowrie [up|down]  # the Cowrie honeypot (see docs/DEMO.md)

The dashboard binds 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

import numpy as np  # noqa: E402

from dloop.logging_config import configure, get_logger  # noqa: E402

DATA_NPZ = ROOT / "data" / "loop" / "cicids.npz"
DEMO_DIR = ROOT / "data" / "demo"
RECORDED = ROOT / "results" / "demo" / "recorded.json"
log = get_logger("scripts.run")


def _build(recorded: bool, with_cowrie: bool):
    from dloop.demo.data import load_demo_data
    from dloop.demo.detector import LiveDetector, RecordedDetector
    from dloop.demo.replay import ReplayDriver
    from dloop.demo.recorded import RecordedLoop
    from dloop.demo.service import DemoService
    from dloop.loop.live import LiveLoop
    from dloop.loop.registry import ModelRegistry
    from dloop.store.sqlite import Store

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    store = Store(DEMO_DIR / "demo.sqlite")
    store.reset(("alerts", "models"))
    registry = ModelRegistry(DEMO_DIR / "registry", store)
    if recorded:
        loop = RecordedLoop(RECORDED, registry)
        fams = json.loads(RECORDED.read_text())["meta"]["stream_families"]
        driver = ReplayDriver(np.zeros((1, 24)), np.zeros((60 * len(fams), 24)), np.repeat(fams, 60), seed=0)
        detector = RecordedDetector(registry)
    else:
        from dloop.adversary.mimicry import assert_disjoint_from_eval
        data = load_demo_data(DATA_NPZ)
        # A1's poison source must never coincide with the trusted evaluation set (CLAUDE.md: leakage invalidates all)
        n = assert_disjoint_from_eval(data.pool_benign_x, data.eval_benign_full_x)
        log.warning("loop data ready", seed_rows=len(data.seed_x), eval_rows=len(data.eval_x), disjoint_checked=n)
        loop = LiveLoop(data, registry)
        atk = data.eval_y == 1
        driver = ReplayDriver(data.eval_benign_full_x, data.eval_x[atk], data.eval_family[atk], seed=0)
        detector = LiveDetector(registry)
    honeypot = None
    if with_cowrie:
        from dloop.honeypot.cowrie import CowrieTailer
        honeypot = CowrieTailer(store)
    from dloop.demo.service import DemoService
    return DemoService(loop=loop, registry=registry, detector=detector, driver=driver, store=store,
                       honeypot=honeypot, recorded=recorded)


def cmd_demo(a) -> int:
    import uvicorn
    from dloop.api.app import create_app

    configure("WARNING")
    if a.recorded and not RECORDED.exists():
        print("no recording yet: run `python scripts/run.py record` first", file=sys.stderr)
        return 2
    service = _build(a.recorded, not a.no_cowrie)
    url = f"http://127.0.0.1:{a.port}"
    print(f"\nDeception Loop demo ({'RECORDED' if a.recorded else 'LIVE'}) at {url}  (Ctrl+C to stop)\n")
    if not a.no_browser:
        webbrowser.open(url)
    uvicorn.run(create_app(service), host="127.0.0.1", port=a.port, log_level="warning")
    return 0


def cmd_record(a) -> int:
    from dloop.demo.data import load_demo_data
    from dloop.demo.recorded import record_story
    from dloop.demo.replay import ReplayDriver
    from dloop.loop.live import LiveLoop
    from dloop.loop.registry import ModelRegistry
    from dloop.store.sqlite import Store

    configure("WARNING")
    data = load_demo_data(DATA_NPZ)
    atk = data.eval_y == 1
    fams = ReplayDriver(data.eval_benign_full_x, data.eval_x[atk], data.eval_family[atk]).families
    loop = LiveLoop(data, ModelRegistry(tempfile.mkdtemp(), Store(":memory:")))
    rec = record_story(loop, RECORDED)
    rec["meta"]["stream_families"] = fams
    RECORDED.write_text(json.dumps(rec))
    print(f"recorded {len(rec['canonical'])} canonical rounds + {list(rec['branches'])} branches -> {RECORDED}")
    return 0


def cmd_test(a) -> int:
    return subprocess.call([sys.executable, "-m", "pytest", *a.pytest_args], cwd=ROOT)


def cmd_cowrie(a) -> int:
    from dloop.honeypot.cowrie import cowrie_control
    return cowrie_control(a.action)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo")
    d.add_argument("--recorded", action="store_true")
    d.add_argument("--port", type=int, default=8000)
    d.add_argument("--no-browser", action="store_true")
    d.add_argument("--no-cowrie", action="store_true", help="do not tail the Cowrie log")
    d.set_defaults(fn=cmd_demo)
    sub.add_parser("record").set_defaults(fn=cmd_record)
    t = sub.add_parser("test")
    t.add_argument("pytest_args", nargs="*")
    t.set_defaults(fn=cmd_test)
    c = sub.add_parser("cowrie")
    c.add_argument("action", nargs="?", default="up", choices=["up", "down", "status"])
    c.set_defaults(fn=cmd_cowrie)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
