# Phase B — exploratory pilot results

**EXPLORATORY. Not a confirmatory result and not cited in the paper.** One short
run on one laptop, with a small benign reference. It exists to show the lab works
end to end — real sessions → live honeypot → `tcpdump` → fixed CICFlowMeter →
flows → labels → the paper's own distance metric — and to get a first sense of
where real-traffic mimicry lands.

## Run

- Lab up on `labnet` (`internal: true`), seed 1. ~6 min benign warmup to learn a
  profile (67 benign sessions), then 300 s of mimic sessions at the HTTP honeypot
  plus one each of a port scan, slow SSH guessing (12 attempts) and canned
  SQLi/XSS probes.
- `tcpdump` captured 12 rotated pcaps; the Dockerised fixed CICFlowMeter
  (`4dd5319`) extracted **146 flows** offline; `label.py` joined them to ground truth.

Label breakdown `(true_intent, policy_label)`:

| | policy 0 (benign) | policy 1 (malicious) |
|---|---:|---:|
| benign | 101 | — |
| poison (mimic) | — | 15 |
| attack (scan/guess/probe) | — | 17 |
| unknown (no GT match) | 4 | 9 |

The two columns disagree exactly where the research says they must: 15 mimic
flows are benign-intent yet auto-labelled malicious. The 9 unknown/policy-1 flows
are honeypot-bound flows no generator logged — nmap's per-port connects and
Cowrie's own session flows; expected background, not a join failure.

## Distance to benign (paper's guard-(c) metric)

| quantity | median | p5 |
|---|---:|---:|
| mimic → nearest benign | **0.396** | 0.252 |
| benign → nearest benign (leave-one-out) | **0.167** | 0.070 |
| twin fraction (δ=0.0015) | **0.0** | |

Cost per mimic flow: ~22 packets, ~2.7 kB, ~2.4 s wall-clock (15 flows / 14
connections total).

## What this says (and does not)

- **The mimic did not reach copy fidelity.** The paper's A1 damage is catastrophic
  only at realized NN ≈ 0.011; these mimic flows sit at 0.396 with a twin fraction
  of 0. A quick profile-based generator producing *fresh* real sessions is
  benign-*shaped* but plainly distinguishable — it is right of the FPR cliff the
  paper located, where A1 does little.
- **The absolute number is not comparable to 0.011.** The benign-to-benign floor
  here is already 0.167 — the reference set is ~101 flows against the paper's
  ~230k, so sparsity inflates every distance. The honest comparison is the ratio:
  the mimic is ~2.4× the benign floor, i.e. clearly outside the benign cluster at
  this fidelity, not near-copy.
- **Reaching copy fidelity in real traffic is the open problem**, and that is the
  point for the rebuttal: the feature-space A1 was an *upper bound*. Doing it for
  real needs either a copy-style mimic (replay captured benign flows back through
  the honeypot) rather than a distributional profile, and/or a much larger benign
  capture so the reference is dense enough for near-copies to exist. Both are
  future work; neither was tuned here.

## Extractor distortions observed

- CICFlowMeter split keep-alive HTTP sessions and emitted short appendix flows, so
  a logged session with several requests maps to one or a few flows — handled by
  the time-window join, not by forcing a 1:1 match.
- A handful of packets were discarded per pcap (TCP reassembly edge cases at
  rotation boundaries); counted in the tool's own `Packet stats`, not corrected.

## Caveat that blocked step 3

Extractor validation against Engelen's published reprocessed CSV is **not done**:
the CICIDS2017 raw PCAPs are gated behind the UNB registration form (see README).
Until that slice is extracted and compared, the pilot's absolute distances cannot
be tied to the paper's reprocessed-CICIDS2017 feature space — only the lab's
internal benign-vs-mimic comparison above stands.
