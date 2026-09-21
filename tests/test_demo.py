import numpy as np
import pytest

from dloop.demo.replay import BURST_TICK_MULTIPLE, RATE_MAX, RATE_MIN, ReplayDriver
from dloop.honeypot.cowrie import CowrieTailer, session_effort


def _driver(rate=100):
    rng = np.random.default_rng(0)
    fams = np.repeat(["DDoS", "PortScan", "SSH-Patator", "Rare"], [200, 100, 100, 5])
    return ReplayDriver(rng.normal(size=(500, 4)), rng.normal(size=(len(fams), 4)), fams, seed=1, rate=rate)


def test_rate_is_clamped_to_the_supported_range_and_flow_count_matches_rate():
    d = _driver(rate=10_000)
    assert d.rate == RATE_MAX
    assert d.set_rate(1) == RATE_MIN
    d.set_rate(100)
    n = sum(len(d.next_tick(0.1)[0]) for _ in range(100))
    assert n == 1000                                   # 100 flows/s for 10 s, fractional carry included


def test_rare_families_are_not_streamed_and_burst_is_visible_then_drains():
    d = _driver()
    assert "Rare" not in d.families
    d.launch("DDoS", 300)
    seen, ticks = 0, 0
    while d.burst_backlog:
        x, fam, inj = d.next_tick(0.1)
        assert inj.sum() <= BURST_TICK_MULTIPLE * len(x) + BURST_TICK_MULTIPLE
        assert (fam[inj] == "DDoS").all() and len(x) == len(fam) == len(inj)
        seen += int(inj.sum())
        ticks += 1
    assert seen == 300 and ticks < 20                  # a 300-flow burst is over in ~1.5 s at 100 flows/s
    with pytest.raises(ValueError):
        d.launch("Nope")


def test_session_effort_is_zero_for_no_effort_and_increases_in_every_component():
    assert session_effort(0, 0, 0, 0) == 0.0
    base = session_effort(2, 2, 100, 5)
    for args in ((3, 2, 100, 5), (2, 3, 100, 5), (2, 2, 200, 5), (2, 2, 100, 6)):
        assert session_effort(*args) > base


def test_cowrie_tailer_builds_sessions_from_a_synthetic_log(tmp_path):
    import json
    log = tmp_path / "cowrie.json"
    ev = [
        {"eventid": "cowrie.session.connect", "session": "s1", "src_ip": "127.0.0.1", "timestamp": "2026-01-01T00:00:00Z"},
        {"eventid": "cowrie.login.failed", "session": "s1", "username": "root", "password": "123456", "timestamp": "2026-01-01T00:00:01Z"},
        {"eventid": "cowrie.login.success", "session": "s1", "username": "root", "password": "admin", "timestamp": "2026-01-01T00:00:02Z"},
        {"eventid": "cowrie.command.input", "session": "s1", "input": "uname -a", "timestamp": "2026-01-01T00:00:03Z"},
        {"eventid": "cowrie.session.closed", "session": "s1", "duration": 4.0, "timestamp": "2026-01-01T00:00:04Z"},
    ]
    log.write_text("".join(json.dumps(e) + "\n" for e in ev) + '{"eventid": "cowrie.command.inp')   # torn last line
    t = CowrieTailer(path=log)
    assert t.poll() == 5
    s = t.snapshot()
    assert s["totals"] == {"sessions": 1, "logins": 2, "login_success": 1, "commands": 1, "distinct_credentials": 2}
    assert s["sessions"][0]["effort"] > 0 and s["sessions"][0]["duration"] == 4.0
    assert t.poll() == 0                               # the torn line is not consumed until it is complete
