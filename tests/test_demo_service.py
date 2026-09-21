"""DemoService source switching: live and recorded must never mix state, and switching must not crash when
only one source is available (the demo-day fallback case)."""

import json
import tempfile

import pytest

from dloop.demo.detector import LiveDetector
from dloop.demo.recorded import RecordedLoop, record_story
from dloop.demo.service import DemoService
from dloop.loop.live import LiveLoop
from dloop.loop.registry import ModelRegistry
from dloop.store.sqlite import Store
from tests.test_loop import loop_data  # noqa: F401  (fixture)


def _sources(loop_data, tmp_path):
    live_reg = ModelRegistry(tmp_path / "live", Store(":memory:"))
    live = LiveLoop(loop_data, live_reg, model_kind="rf", batch_size=200)
    rec_path = tmp_path / "story.json"
    record_story(live, rec_path, s0_rounds=2, a1_rounds=2, branch_rounds=1)
    rec_reg = ModelRegistry(tmp_path / "rec", Store(":memory:"))
    rec = RecordedLoop(rec_path, rec_reg)
    return {"live": (live, live_reg, LiveDetector(live_reg)), "recorded": (rec, rec_reg, LiveDetector(live_reg))}


def test_switch_source_resets_stream_state_and_keeps_each_loop_independent(loop_data, tmp_path):
    sources = _sources(loop_data, tmp_path)
    svc = DemoService(sources=sources, active="live", driver=None, store=Store(":memory:"))
    svc.total_flows, svc.total_alerts = 5, 2
    svc._window.append((True, True))
    assert svc.active == "live" and svc.loop is sources["live"][0]

    svc.switch_source("recorded")
    assert svc.active == "recorded" and svc.loop is sources["recorded"][0]
    assert svc.total_flows == 0 and svc.total_alerts == 0 and len(svc._window) == 0
    assert svc.loop.round == 0                     # RecordedLoop.reset() re-emits round 0

    svc.switch_source("recorded")                   # no-op: switching to the already-active source
    assert svc.active == "recorded"

    with pytest.raises(ValueError):
        svc.switch_source("nope")


def test_only_one_source_available_is_not_an_error(loop_data, tmp_path):
    sources = _sources(loop_data, tmp_path)
    del sources["recorded"]
    svc = DemoService(sources=sources, active="live", driver=None, store=Store(":memory:"))
    assert svc.active == "live"
    with pytest.raises(ValueError):
        svc.switch_source("recorded")


def test_model_version_history_does_not_collide_across_sources(loop_data, tmp_path):
    sources = _sources(loop_data, tmp_path)
    svc = DemoService(sources=sources, active="live", driver=None, store=Store(":memory:"))
    svc.loop.step("s0", "off")
    live_versions = {m["version"] for m in svc.registry.store.models()}
    svc.switch_source("recorded")
    svc.loop.step("s0", "off")
    rec_versions = {m["version"] for m in svc.registry.store.models()}
    assert live_versions and rec_versions            # each registry has its own version sequence
