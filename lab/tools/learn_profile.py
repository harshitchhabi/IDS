"""Learn a benign profile from the lab's own benign ground-truth (Phase B).

The adversary's mimic mode replays this profile toward the honeypots. Keeping the
profile empirical (observed samples, not fitted parameters) means the mimic
reproduces the lab's actual benign session shapes, which is what makes the A1
flows statistically close to production benign traffic.

Fields: per-session request counts, byte counts and durations for web; command
counts and durations for ssh; and the inter-arrival gaps between consecutive
benign session starts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from label import parse_ground_truth


def build_profile(gt_paths: list[Path]) -> dict:
    gt = parse_ground_truth(gt_paths)
    benign = gt[gt["intent"] == "benign"].sort_values("t_start") if not gt.empty else gt
    prof: dict = {"web": {}, "ssh": {}, "inter_arrival": []}
    if benign.empty:
        return prof

    web = benign[benign["kind"] == "web"]
    ssh = benign[benign["kind"] == "ssh"]
    if not web.empty:
        prof["web"] = {
            "requests_per_session": [int(x) for x in web.get("requests", []).fillna(0)],
            "bytes": [int(x) for x in web.get("bytes", []).fillna(0)],
            "think_times": [0.5, 1.0, 1.5, 2.0],  # placeholder; refined below if durations exist
            "duration_s": [round(float(d), 3) for d in (web["t_end"] - web["t_start"])],
        }
        # Approximate think times as per-request share of session duration.
        tt = []
        for _, r in web.iterrows():
            nreq = max(1, int(r.get("requests", 1) or 1))
            tt.append(round(float(r["t_end"] - r["t_start"]) / nreq, 3))
        if tt:
            prof["web"]["think_times"] = tt
    if not ssh.empty:
        prof["ssh"] = {
            "commands_per_session": [int(x) for x in ssh.get("commands", []).fillna(0)],
            "duration_s": [round(float(d), 3) for d in (ssh["t_end"] - ssh["t_start"])],
        }

    starts = benign["t_start"].to_numpy()
    prof["inter_arrival"] = [round(float(g), 3) for g in (starts[1:] - starts[:-1])] or [1.5]
    prof["n_sessions"] = int(len(benign))
    return prof


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ground-truth", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    prof = build_profile(list(args.ground_truth))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(prof, indent=2))
    print(f"wrote {args.out}: {prof.get('n_sessions', 0)} benign sessions profiled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
