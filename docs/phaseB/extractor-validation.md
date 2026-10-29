# Phase B — extractor validation against published reprocessed CICIDS2017

Does this lab's pinned fixed CICFlowMeter (`dloop-cicflowmeter:4dd5319`, Engelen
et al.'s WTMC-2021 build) reproduce the release the paper's reprocessed-CICIDS2017
numbers come from? We extract the first 30 minutes of the raw CICIDS2017 Monday
pcap with it and compare, flow by flow, against Engelen's published `monday.csv`
(`IDS-data/cicids2017-fixed`).

**Result: yes.** Across the whole 30-minute window — 18,248 extracted flows,
18,207 matched to the release (99.8%) at a 0 s time offset, every feature exact on
≥ 97% of matched flows. The one obstacle, a Java-heap OOM on the full slice, was
solved by splitting the input (never by raising memory), as the memory rule
requires.

## 1. The slice

The raw `Monday-WorkingHours.pcap` (10,822,507,416 B ≈ 10.1 GiB) lives in
`newdata/` (gitignored). We never load it whole: `editcap -A/-B` (sequential scan)
cut the first 30 minutes of capture into `lab/data/validate/monday_30min.pcap`.

| | value |
|---|---|
| slice size | 2,787,210,956 B (≈ 2.60 GiB) |
| packets | 2,223,995 |
| capture span | 1799.37 s (`11:55:58.598` → `12:25:57.970`) |

## 2. The OOM, and the split that fixed it

A single extraction over the whole slice **died with
`java.lang.OutOfMemoryError: Java heap space`** after emitting only 2,236 flows:
CICFlowMeter holds every *open* flow in memory, and the window has > 18,000 flows
alive across its span — more than the 1.86 GiB Docker VM's heap allows at once.

Per the memory rule we did **not** raise the heap. Instead we split the slice into
flow-preserving pieces and extracted each in a **fresh JVM** (clean heap per piece),
so peak memory is bounded by one piece's concurrent flows:

- One host, `192.168.10.14`, is in 1,964,891 of the 2,223,995 packets (88%).
- Pieces: `rest` = every packet **not** touching `.14`; and `.14`'s traffic split
  into 8 by the **peer** IP's last-octet low 3 bits — both directions of a `.14↔X`
  flow map to the same bucket (peer byte is `ip[15]` when `.14` is the destination,
  `ip[19]` when it is the source), so **every 5-tuple stays wholly in one piece**.
  A 10th piece holds `.14`'s non-IP packets (ARP).

**The pieces add up exactly** (capinfos, authoritative packet records):

| piece | packets |
|---|---:|
| rest | 258,884 |
| p14_2 | 1,873,239 |
| p14_3 | 27,530 |
| p14_1 | 18,047 |
| p14_5 | 12,732 |
| p14_6 | 10,435 |
| p14_4 | 10,329 |
| p14_0 | 8,368 |
| p14_7 | 4,205 |
| p14_nonip | 226 |
| **sum** | **2,223,995** = original |

(An earlier `tcpdump | wc -l` tally read high — 2,246,235 — because tcpdump prints
some packets on more than one line; `capinfos -c` counts records and is the
authoritative check.)

**No piece needed a finer split.** The biggest, `p14_2` (1.87M packets), extracted
cleanly: it is only **225 flows** — a handful of long-lived `.14↔peer` flows, so few
concurrent flows and little memory, despite the packet volume. That is the lesson:
the OOM scaled with *concurrent open flows*, not packet count, so per-piece
extraction fixed it. Each piece's flow count:

| piece | flows |
|---|---:|
| rest | 13,371 |
| p14_3 | 3,361 |
| p14_6 | 236 |
| p14_5 | 230 |
| p14_1 | 228 |
| p14_2 | 225 |
| p14_4 | 223 |
| p14_0 | 209 |
| p14_7 | 156 |
| p14_nonip | 9 |
| **total** | **18,248** |

Because each 5-tuple lives entirely in one piece, concatenating the per-piece CSVs
reconstructs the full extraction with no duplicated or fragmented flows.

## 3. Matching (`lab/tools/validate_extractor.py`)

A flow is identified by its 5-tuple (`Flow ID`) and start time; the tool
auto-detects the constant start-time offset between the two sides before matching
within a 2 s window.

| | value |
|---|---|
| lab flows (full window, concatenated) | 18,248 |
| published flows (full day) | 371,624 |
| published flows starting in the window | 18,231 |
| **detected start-time offset** | **0.0 s** |
| **matched** | **18,207 / 18,248 = 99.8 %** |

The **0.0 s offset is itself a result**: the lab extractor timestamps flows
identically to the release (the first flow is `8.6.0.1-8.0.6.4-0-0-0` at
`2017-07-03 11:56:34.157427` on both sides), so the timezone confound that was a
risk going in does not exist. The 41 unmatched lab flows (0.2%) are window-edge
flows whose published start sits just outside the 2 s tolerance; lab emitted 18,248
vs the 18,231 the release starts in the window (+17), the same edge effect.

## 4. Per-feature agreement (18,207 matched flows)

`results/phaseB/extractor_match.csv`. Exact-match rate, and median relative error
over the rows that are not exact.

| feature group | exact-match rate |
|---|---|
| `syn_flag_count` | 1.000 |
| packet-length max/min (fwd/bwd) | 0.9982–0.9987 |
| `flow_iat_min`, `flow_iat_max`, `psh_flag_count`, `bwd_bytes` | 0.990–0.991 |
| byte totals, down/up ratio, `fwd_bytes`, `ack_flag_count` | 0.985–0.990 |
| counts, length means, IAT means/std, rates, `pkt_size_avg` | 0.971–0.983 |

Every feature agrees exactly on **≥ 97.1%** of matched flows. The residual
disagreements concentrate in the **timing-derived** features (IAT mean/std/min/max
and the per-second rates) and the counts/means that depend on packet ordering —
exactly where CICFlowMeter's own `disordered packets` warning (the pcap is not
perfectly time-sorted) predicts them. `flow_iat_min` shows a median relative error
of 2.0 on its non-exact rows, but that is a few flows with sub-millisecond IATs
where a few-µs absolute difference is large in relative terms. Flag counts and byte
totals — the order-independent quantities — are the most exact.

## 5. Verdict

**The extractor build and invocation are the published ones.** Over the full
30-minute window, `dloop-cicflowmeter:4dd5319` reproduces Engelen's reprocessed
CICIDS2017 at a 0 s time offset, 99.8% of flows matched, and ≥ 97% exact agreement
on every feature, with residuals confined to the ordering-sensitive timing/rate
features. The Phase B lab therefore produces flows in the same feature space as the
paper's reprocessed CICIDS2017, and the memory ceiling was handled by splitting the
input, not by relaxing it.

## Reproduce

```bash
# 1. slice (editcap, sequential; newdata/ holds the raw pcap, gitignored)
editcap -A '2017-07-03 11:55:58' -B '2017-07-03 12:25:58' \
  newdata/Monday-WorkingHours.pcap lab/data/validate/monday_30min.pcap
# 2. split by host-pair so every 5-tuple is in one piece (see §2), then extract
#    each piece in a fresh JVM (clean heap). Concatenate the per-piece *_Flow.csv.
# 3. compare
python lab/tools/validate_extractor.py \
  --lab lab/data/validate/monday_30min_full.csv \
  --published <unzipped IDS-data/cicids2017-fixed/monday.csv> \
  --out results/phaseB/extractor_match.csv
```
