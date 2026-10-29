"""Phase B (packet-level lab) unit tests: the flow<->ground-truth join and the
canonical feature mapping in lab/tools/label.py. These run with no containers and
no data — small hand-built frames only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

# lab/tools is not a package on the path; add it so `import label` works.
_TOOLS = Path(__file__).resolve().parents[1] / "lab" / "tools"
sys.path.insert(0, str(_TOOLS))

import label  # noqa: E402
from dloop.features import schema  # noqa: E402

HONEYPOT = "172.28.0.21"
PROD = "172.28.0.10"
ATTACKER = "172.28.0.40"
BENIGN = "172.28.0.30"


def _ts(epoch: float) -> str:
    # Build an extractor-style timestamp string that _flow_ts_seconds round-trips
    # back to the same epoch (both treated as UTC), so the join is deterministic.
    return pd.to_datetime(epoch, unit="s").strftime("%Y-%m-%d %H:%M:%S.%f")


def _raw_flow(**over) -> dict:
    """A flow row in Engelen fixed-CICFlowMeter column names, zero-filled."""
    row = {c: 0 for c in schema.CICIDS_FIXED_COLUMN_MAP}
    row.update({"Flow ID": "f", "Src IP": BENIGN, "Dst IP": PROD, "Src Port": 5000,
                "Dst Port": 80, "Timestamp": _ts(1000.0)})
    row.update(over)
    return row


def test_policy_label_keys_on_honeypot_destination():
    assert label.policy_label(HONEYPOT) == 1
    assert label.policy_label(PROD) == 0
    assert label.policy_label("8.8.8.8") == 0


def test_map_to_canonical_renames_and_selects():
    flows = pd.DataFrame([_raw_flow(), _raw_flow()])
    out = label.map_to_canonical(flows)
    assert list(out.columns) == list(schema.CANONICAL_FEATURES)
    assert len(out) == 2


def test_map_to_canonical_raises_on_missing_feature():
    flows = pd.DataFrame([_raw_flow()]).drop(columns=["Flow Duration"])
    with pytest.raises(KeyError):
        label.map_to_canonical(flows)


def test_parse_ground_truth_reads_jsonl(tmp_path):
    p = tmp_path / "gt.jsonl"
    p.write_text(
        json.dumps({"src": BENIGN, "dst": PROD, "dst_port": 80, "t_start": 1.0,
                    "t_end": 2.0, "intent": "benign", "kind": "web"}) + "\n\n"
        + json.dumps({"src": ATTACKER, "dst": HONEYPOT, "dst_port": 80, "t_start": 5.0,
                      "t_end": 6.0, "intent": "poison", "kind": "mimic_web"}) + "\n")
    gt = label.parse_ground_truth([p])
    assert len(gt) == 2
    assert set(gt["intent"]) == {"benign", "poison"}


def test_label_flows_divergence_between_policy_and_intent(tmp_path):
    # A mimic flow to the honeypot: policy says malicious, truth says poison —
    # the divergence the research is about. A benign flow to prod agrees on both.
    # A flow to the honeypot with no matching ground truth is unknown/malicious.
    gt_path = tmp_path / "gt.jsonl"
    gt_path.write_text(
        json.dumps({"src": BENIGN, "dst": PROD, "dst_port": 80, "t_start": 990.0,
                    "t_end": 1010.0, "intent": "benign", "kind": "web"}) + "\n"
        + json.dumps({"src": ATTACKER, "dst": HONEYPOT, "dst_port": 80, "t_start": 1990.0,
                      "t_end": 2010.0, "intent": "poison", "kind": "mimic_web"}) + "\n")
    gt = label.parse_ground_truth([gt_path])
    flows = pd.DataFrame([
        _raw_flow(**{"Src IP": BENIGN, "Dst IP": PROD, "Dst Port": 80, "Timestamp": _ts(1000.0)}),
        _raw_flow(**{"Src IP": ATTACKER, "Dst IP": HONEYPOT, "Dst Port": 80, "Timestamp": _ts(2000.0)}),
        _raw_flow(**{"Src IP": ATTACKER, "Dst IP": HONEYPOT, "Dst Port": 80, "Timestamp": _ts(9999.0)}),
    ])
    out = label.label_flows(flows, gt)
    assert out.loc[0, "policy_label"] == 0 and out.loc[0, "true_intent"] == "benign"
    assert out.loc[1, "policy_label"] == 1 and out.loc[1, "true_intent"] == "poison"
    assert out.loc[2, "policy_label"] == 1 and out.loc[2, "true_intent"] == "unknown"


def test_match_intent_unknown_without_ground_truth():
    empty = label.parse_ground_truth([])
    flow = pd.Series({"Src IP": BENIGN, "Dst IP": PROD, "Dst Port": 80, "_ts_s": 1000.0})
    assert label.match_intent(flow, empty) == "unknown"


def test_validate_extractor_matches_on_flowid_and_offset_start_time():
    # Same flows on both sides but the published side is shifted +3h (a timezone
    # representation difference). The matcher must detect the offset and still match,
    # 5-tuple + offset-corrected start time. (Phase B extractor validation.)
    import importlib
    ve = importlib.import_module("validate_extractor")

    def row(fid, ts, dur, fwd):
        return {"Flow ID": fid, "Timestamp": ts, "Flow Duration": dur, "Total Fwd Packet": fwd}

    lab = pd.DataFrame([
        row("a-b-1-2-6", "2017-07-03 13:15:58", 100, 5),
        row("c-d-3-4-6", "2017-07-03 13:16:10", 200, 9),
    ])
    pub = pd.DataFrame([
        row("a-b-1-2-6", "2017-07-03 10:15:58", 100, 5),   # +(-3h), identical features
        row("c-d-3-4-6", "2017-07-03 10:16:10", 200, 7),   # same flow, fwd differs
        row("z-z-9-9-6", "2017-07-03 09:00:00", 1, 1),      # unrelated day flow
    ])
    merged, diag = ve.match(lab, pub, offset=None, tolerance=2.0)
    assert diag["offset_s"] == -10800.0           # -3h auto-detected
    assert diag["n_matched"] == 2                 # both lab flows matched
    agree = ve.feature_agreement(merged, features=("flow_duration", "fwd_packets"))
    dur = agree.set_index("feature").loc["flow_duration"]
    fwd = agree.set_index("feature").loc["fwd_packets"]
    assert dur["exact_match_rate"] == 1.0         # duration identical on both
    assert fwd["exact_match_rate"] == 0.5         # one of two fwd_packets differs


# --- Phase B lab dataset + replay adversary (DECISIONS §32) ---

def _canon_cols():
    return list(schema.CANONICAL_FEATURES)


def test_lab_replay_adversary_emits_pool_rows_true_benign():
    import numpy as np
    from dloop.adversary.base import features_of
    from dloop.adversary.lab_replay import LabReplayAdversary
    pool = np.arange(5 * len(schema.CANONICAL_FEATURES), dtype="float64").reshape(5, -1) + 1.0
    adv = LabReplayAdversary(pool, seed=1)
    batch, cost = adv.generate_batch(1, 3)
    assert len(batch) == 3
    assert (batch["true_label"].to_numpy() == 0).all()      # truly benign
    # emitted rows are drawn from the pool, unchanged (no jitter)
    x = features_of(batch)
    poolset = {tuple(r) for r in pool}
    assert all(tuple(r) in poolset for r in x)
    assert cost.flows == 3


def test_build_lab_partitions_roles_disjoint_and_pool_is_mimic():
    import numpy as np
    import pandas as pd
    from dloop.sim.lab import LabSplitConfig, build_lab_partitions
    rng = np.random.default_rng(0)
    cols = _canon_cols()

    def block(n, base, intent, kind):
        x = rng.uniform(base, base + 1, size=(n, len(cols))) + np.arange(n)[:, None] * 10.0
        d = pd.DataFrame(x, columns=cols)
        d["true_intent"] = intent; d["true_kind"] = kind
        d["policy_label"] = 1 if intent in ("poison", "attack") else 0
        return d

    df = pd.concat([
        block(200, 1.0, "benign", "web"),
        block(40, 500.0, "attack", "portscan"),
        block(60, 1000.0, "poison", "mimic_oracle"),
        block(60, 2000.0, "poison", "mimic_profile"),
    ], ignore_index=True)
    data = build_lab_partitions(df, LabSplitConfig(primary_strategy="oracle"))
    for p in ("seed_train", "prod_benign", "honeypot_pool", "trusted_eval"):
        assert p in data.frames and len(data.frames[p]) > 0
    # honeypot_pool is the oracle mimic flows, all true-benign (BINARY_LABEL 0)
    pool = data.frames["honeypot_pool"]
    assert (pool[schema.BINARY_LABEL] == 0).all()
    assert len(pool) == 60
    # 24-feature schema preserved and in canonical order
    assert tuple(data.features) == schema.CANONICAL_FEATURES
    # the build asserts trusted_eval disjoint from training internally; reaching
    # here without raising means it held.
