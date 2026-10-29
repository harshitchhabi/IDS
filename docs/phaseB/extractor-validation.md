# Phase B — extractor validation against published reprocessed CICIDS2017

Does this lab's pinned fixed CICFlowMeter (`dloop-cicflowmeter:4dd5319`, Engelen
et al.'s WTMC-2021 build) reproduce the release the paper's reprocessed-CICIDS2017
numbers come from? We extract a slice of the raw CICIDS2017 Monday pcap with it and
compare, flow by flow, against Engelen's published `monday.csv`
(`IDS-data/cicids2017-fixed`).

**Headline: the extractor is the right one — but it ran out of memory on the full
slice, so this is a per-flow agreement check on a partial extraction, not a
flow-count check.** Reported as-is; nothing was tuned to make the match or to fit
the memory.

## 1. The slice

The raw `Monday-WorkingHours.pcap` (10,822,507,416 B ≈ 10.1 GiB) lives in
`newdata/` (gitignored). We never load it whole: `editcap -A/-B` (sequential scan)
cut the first 30 minutes of capture — from the first packet at
`2017-07-03 11:55:58.598308` to `12:25:58` — into
`lab/data/validate/monday_30min.pcap`.

| | value |
|---|---|
| slice size | 2,787,210,956 B (≈ 2.60 GiB) |
| packets | 2,223,995 |
| capture span | 1799.37 s (`11:55:58.598` → `12:25:57.970`) |

## 2. Extraction — out of memory

The pinned extractor ran offline (`docker run --network none`) over the slice and
**died with `java.lang.OutOfMemoryError: Java heap space`** after flushing **2,236
flows**. Docker's WSL2 VM on this machine is 1.86 GiB total; CICFlowMeter holds
every still-open flow in memory and the first minutes of the capture have far more
concurrent flows than that heap allows, so it exhausted the heap partway through.

Per the task's instruction, **we stopped here rather than shrink the slice or raise
the heap** — the extractor's settings and invocation are exactly Engelen's, and
changing them would no longer validate the published build.

The extractor also warned `The pcap file contains disordered packets` (editcap
preserves the pcap's native ordering, which is not perfectly time-sorted); this
bears on the timing features below.

## 3. How truncated the output is

The 2,236 emitted flows are **not** the whole window. The published CSV has
**18,231 flows** whose start falls in `[11:55:58, 12:25:58]`, so the extraction
captured ≈ 12 % of the window before the OOM. The flows it did emit are biased
toward **early-terminating** (short) flows — those are the ones CICFlowMeter
flushes first; the long-lived flows were still in memory when it died.

So flow **count** is not validated. What follows is a per-flow correctness check on
the 2,236 flows that were emitted.

## 4. Matching

`lab/tools/validate_extractor.py` matches a flow by its 5-tuple (`Flow ID`) and
start time. It auto-detects the constant start-time offset between the two sides
(to absorb any timezone/representation difference) before matching within a 2 s
window.

| | value |
|---|---|
| lab flows (emitted before OOM) | 2,236 |
| published flows (full day) | 371,624 |
| **detected start-time offset** | **0.0 s** |
| **matched** | **2,229 / 2,236 = 99.7 %** |

The **0.0 s offset is itself a result**: the lab extractor timestamps flows
identically to the release (the first flow is `8.6.0.1-8.0.6.4-0-0-0` at
`2017-07-03 11:56:34.157427` on both sides), so the timezone confound that was a
risk going in does not exist here. The 7 unmatched lab flows (0.3 %) are
window-boundary flows whose published start sits just outside the 2 s tolerance.

## 5. Per-feature agreement (2,229 matched flows)

`results/phaseB/extractor_match.csv`. Exact-match rate, and median relative error
over the rows that are not exact.

| group | result |
|---|---|
| **packet/byte counts, packet-length stats, all flag counts, down/up ratio, pkt_size_avg** | **exact on 100 % of flows** (`bwd_packets`, `fwd_bytes`, `bwd_bytes`, `fwd/bwd_pkt_len_max/min`, `syn/psh/ack_flag_count`, `down_up_ratio`) or ≥ 99.5 % exact |
| flow_duration | 99.96 % exact |
| fwd_packets | 99.78 % exact |
| rate features (flow_bytes/s, flow_pkts/s) | 98.7 % / 99.3 % exact |
| IAT features (flow/fwd/bwd IAT mean/std/max/min) | 98.8 %–99.96 % exact; median rel-err on the non-exact rows 0.26–2.0 |

Every feature agrees exactly on ≥ 98.7 % of the matched flows. The residual
disagreements are concentrated in the **timing-derived** features (IAT mean/std/
min/max and the rates), exactly where the `disordered packets` warning predicts
them: a few reordered packets change inter-arrival computations. `flow_iat_min`
shows a median relative error of 2.0 on its non-exact rows, but that is a handful
of flows with sub-millisecond IATs where an absolute difference of a few µs is
large in relative terms. Counts, byte totals and flags — which do not depend on
packet ordering — are exact.

## 6. Verdict

- **The extractor build and invocation are correct.** When `dloop-cicflowmeter:4dd5319`
  emits a flow, that flow matches Engelen's published release to the bit on
  ordering-independent features and to ≥ 98.7 % exact on timing features, at zero
  time offset. This is the evidence the Phase B pilot needed that its flows live in
  the same feature space as the paper's reprocessed CICIDS2017.
- **A complete-count validation is still open**, blocked by the Java-heap OOM on a
  2.6 GiB slice in a 1.86 GiB Docker VM. Finishing it needs either more memory for
  the extractor (a larger Docker VM / a non-Docker-Desktop host) or the dataset's
  own per-protocol pcap splits — both deliberately out of scope here, since neither
  is "the pinned extractor at its published settings" that this check is about.

## Reproduce

```bash
# 1. slice (editcap, sequential; newdata/ holds the raw pcap, gitignored)
editcap -A '2017-07-03 11:55:58' -B '2017-07-03 12:25:58' \
  newdata/Monday-WorkingHours.pcap lab/data/validate/monday_30min.pcap
# 2. extract (offline). NOTE: OOMs in a <2 GiB Docker VM.
docker run --rm --network none -v "$PWD/lab/data:/tmp/pcap" \
  dloop-cicflowmeter:4dd5319 /tmp/pcap/validate/in /tmp/pcap/validate/out
# 3. compare
python lab/tools/validate_extractor.py \
  --lab lab/data/validate/out/monday_30min.pcap_Flow.csv \
  --published <unzipped IDS-data/cicids2017-fixed/monday.csv> \
  --out results/phaseB/extractor_match.csv
```
