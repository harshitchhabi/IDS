# Deception Loop — Project Context

Read this before writing code. It defines the architecture, the constraints, and
the phase you are in.

---

## What this is

A deception-aware network intrusion detection system that continuously retrains
itself from honeypot-derived labels — **and** a research harness that attacks
that design and defends it.

Two deliverables from one codebase:

1. **The system.** A working NIDS: live traffic capture, flow feature
   extraction, ML detection, integrated honeypots, auto-labeling, periodic
   retraining, and a real-time dashboard. Must be demoable end-to-end.
2. **The research.** Evidence that the auto-labeling loop is an
   attacker-controlled write channel into the defender's training set, plus a
   defense. This is the paper.

The system is not a demo wrapper around the research. The research is a set of
scenarios run against a system that genuinely works.

---

## Threat model (the research depends on getting this right)

Current literature integrates honeypots with ML-based IDS to solve the
labeled-data problem. The argument: any traffic reaching a decoy is unsolicited
by definition, so honeypot interactions are free, self-labeling ground-truth
malicious samples. Feed them into retraining and you get continuous adaptation
with no human annotator.

The unexamined assumption is that honeypot labels are trustworthy *because* the
source is a decoy. But the attacker controls exactly what the decoy sees, and
the labeling policy ("everything the honeypot sees is malicious") is public. The
honeypot is therefore a write channel into the defender's training set — one the
defender opens deliberately. The poison budget is not a fraction the attacker
must fight for; it is the entire honeypot-derived share of the training set.

### Scenarios to support

| ID | Name | Description |
|----|------|-------------|
| **S0** | Clean | Adversary sends genuine attacks to the decoy. Labels correct. Detector should **improve**. This must work before anything else means anything. |
| **A1** | Benign mimicry | Adversary sends the decoy traffic statistically indistinguishable from production benign traffic. Auto-labeled malicious. Retrained detector flags real users. FPR blows up. Costs the attacker nothing. |
| **A2** | Boundary drift | Adversary walks decoy-visible attack traffic gradually toward the benign region across rounds, dragging the boundary so a withheld real payload lands on the benign side. Evasion by teaching. *(Phase 5, stretch.)* |
| **A4** | Fingerprint-and-split | Adversary identifies decoy hosts and shows them only a subset of its TTPs. Not poisoning — selective disclosure. Training distribution becomes one the attacker chose. |

### Defenses

Status reflects the Phase 0 results (docs/DECISIONS.md §20-25). The original plan cast D1 as the novel
contribution; the measurements did not support that.

| ID | Name | Status |
|----|------|--------|
| **ShareCap** | Cap the honeypot's effective share of the training set at `c` (uniform weight `min(1, c/(1-c) * n_seed/n_honeypot)`, recomputed each retrain). No cost, label or feature information, no trusted data, no knowledge of the poison ratio. | **Recommended defense.** At c=0.05 it recovers ~100% of A1 damage at poison ratios 0.5 and 0.9 and keeps 0.81 (CICIDS) to 0.99 (synthetic) of the honest loop's gain. No D1 variant, kNN or fixed uniform weight dominates it (0 of 87 cases). The cap depends on where damage starts for a given model and dataset (DECISIONS §25.5). |
| **D1** | Cost-of-influence weighting (per-flow effort from duration, packets, bytes, protocol depth) | **Measured negative result.** It does not beat a no-skill baseline: uniform w=0.05 matches its recovery at ratio 0.5, ShareCap beats it at every ratio, and on CICIDS (effort AUROC 0.81) no variant dominates kNN. The pre-registered insensitivity criterion (§20) failed, 2 of 12. What stands: protection comparable to kNN at ~781x lower overhead (0.000216 vs 0.168 s/round). Per-flow cost proxies are insufficient; session-level effort is untested (future work, §25.6). |
| **kNN sanitize / loss filter** | Generic label-cleaning baselines | kNN against the trusted seed set works but is ~781x costlier than D1. **Loss filtering fails structurally** (recovery -0.005): the poison carries the defender's *own* labelling policy, so it looks consistent to a label-consistency filter. References anchored outside the loop work; filters inside it do not (§23, "policy-consistency blind spot"). |
| **D2** | Do-no-harm admission gate | Not built. |
| **D3** | Persona randomization | Not built. |

**Nice property to exploit in the demo:** A1 is literally "point the benign
traffic generator at the honeypot instead of production." Reuse the generator
code. It makes the threat visceral in about ten seconds of demo.

---

## Architecture

```
docker/compose.yml
│
├── prod-net ─────────── nginx · openssh · mysql · benign-traffic-generator
├── decoy-net ────────── cowrie (SSH/Telnet) · http-honeypot · service-decoys
├── attacker-net ─────── nmap · hydra · hping3 · scenario scripts
└── defense-net ──────── sensor · detector · retrainer · api · dashboard
```

Data path:

```
traffic ──► sensor (nfstream) ──► flow records ──► store
                                                     │
honeypot logs ──► log tailer ──► interaction events ─┤
                                                     ▼
                                          labeler (auto-label policy)
                                                     │
                                          defense hooks (D1/D2)
                                                     ▼
                                          retrainer ──► model registry
                                                     │
                                          detector ◄──┘
                                                     ▼
                                          alerts ──► api ──► dashboard
```

### Package layout

```
src/dloop/
  capture/     nfstream sensor, pcap replay, flow schema
  honeypot/    cowrie/http log tailers, interaction-cost extraction
  features/    feature schema, cleaning, normalization (single source of truth)
  store/       sqlite (events, alerts, models) + parquet (feature batches)
  models/      rf, xgboost, lstm, autoencoder behind one interface
  loop/        labeler, retrainer, model registry, round scheduler
  defense/     d1_cost_weighting, d2_admission_gate, d3_personas
  adversary/   live scenario drivers + offline adversary implementations
  sim/         Phase 0 offline simulator (shares models/, loop/, defense/)
  api/         fastapi: alerts, metrics, model history, scenario control
dashboard/     jinja + htmx + chart.js (no build step)
experiments/   one script per research question, each emits csv + png
tests/
results/
docs/
```

**Critical:** `sim/` and the live system share `models/`, `loop/`, and
`defense/`. The offline simulator is not a separate prototype — it is the same
code driven by synthetic batches instead of live flows. Results must be
consistent between them, and if they are not, that is a bug worth investigating.

---

## Technology decisions (locked — do not substitute)

- **Python 3.11+**, `uv` for dependency management, pinned versions.
- **nfstream** for flow features. *Not* CICFlowMeter — it has documented
  extraction bugs a reviewer may raise.
- **Cowrie** (`cowrie/cowrie` image) for SSH/Telnet. Plus a custom Flask HTTP
  honeypot and lightweight banner decoys for MySQL/FTP. Skip Dionaea — the build
  friction is not worth it.
- **SQLite** for events/alerts/model metadata (inspectable, zero setup),
  **Parquet** for feature batches.
- **scikit-learn + xgboost + PyTorch.** All models behind one interface that
  supports `sample_weight` — D1 depends on this.
- **FastAPI + Jinja + HTMX + Chart.js.** No React, no build step. WebSocket for
  the live alert feed.
- **Docker Compose** for the whole testbed. `make demo` brings it up.

---

## Safety constraints (non-negotiable)

- The testbed is **lab-internal only**. Honeypots must never bind to a
  public interface. Compose networks are `internal: true` except where
  explicitly required.
- Attack tooling runs only against containers in this compose project. Scenario
  scripts must validate target addresses against an allowlist before firing.
- No captured credentials, keys, or payloads from real systems ever enter the
  repo. Honeypot logs committed as fixtures must be synthetic.
- `results/` may contain data; `data/` is gitignored.

---

## Engineering conventions

- Fixed seeds everywhere (numpy, sklearn, torch). Experiment results must be
  reproducible bit-for-bit from a config.
- Every experiment run writes a config hash alongside its results. A figure must
  be traceable to the exact config that produced it.
- Structured logging (`structlog` or stdlib `logging` with JSON), never `print`.
  I need to see what got dropped during cleaning.
- Type hints on all public interfaces. Docstrings explaining *why*, not *what*.
- `pytest` for: feature-schema stability, partition disjointness, adversary
  batch shape/labels, metric correctness on hand-computed toy cases, cost
  function monotonicity, end-to-end smoke test on synthetic data.
- The entire pipeline must run on **synthetic data with no external downloads**.
  Every phase ships a synthetic fallback. Nothing may hard-require CICIDS2017.
- `make` targets: `demo`, `test`, `sim`, `experiment-<id>`, `figures`, `clean`.

### Metrics discipline

Report **FPR and TPR**, never bare accuracy — the classes are wildly imbalanced
and accuracy will look great while the system is useless. Every evaluation runs
against a `trusted_eval` set that is never touched by the loop. Assert its
disjointness from training data in code; leakage silently invalidates everything.

Per round, record: FPR on trusted benign, TPR on trusted attacks, precision, F1,
AUROC, full confusion matrix, poison ratio (honeypot rows / total training rows),
and attacker cost (flows, packets, bytes, wall-clock).

---

## Phases

> **Revised plan.** The research (Phase 0, plus the defenses of Phase 5) ran entirely offline; its results
> are final and no further experiments are planned beyond the ShareCap cap curve (DECISIONS §25.5). The
> **replay-driven live demo (branch `phase2/demo`) replaces the Phase 1-2 compose testbed** and is the
> course deliverable: CICIDS flows replayed through the detector, the real loop code driven from a control
> panel, and a real Cowrie honeypot shown as a separate telemetry panel. Phases 1, 3, 4 below are the
> original plan, kept for reference and not scheduled. Cowrie sessions are not CICFlowMeter flows and do not
> feed the model.

Build in order. Stop at each checkpoint and report before moving on.

### Phase 0 — Offline simulator *(start here)*
Pure-Python loop simulator. No containers. Model the honeypot abstractly as "a
batch of flows the adversary chooses, which the defender stamps malicious."
Data from CICIDS2017 CSVs with a synthetic fallback generator.

Partition into four **disjoint** sets, split by capture day to avoid temporal
leakage: `seed_train`, `prod_benign`, `honeypot_pool`, `trusted_eval`.

CICIDS2017 gotchas to handle explicitly: whitespace in column names (the label
column is literally `' Label'`), NaN/Inf in `Flow Bytes/s` and
`Flow Packets/s`, duplicate rows, severe class imbalance. Log everything dropped.

**Checkpoint:** S0 shows the clean loop *improving* the detector over rounds,
and A1 shows a measurable FPR increase. If S0 does not improve the detector,
stop — the setup is wrong and there is no point continuing.

### Phase 1 — Testbed and capture
Compose stack up. Benign traffic generator producing realistic mixed traffic
(HTTP browsing, DNS, SSH sessions, file transfer, MySQL queries) on Poisson-ish
timing with diurnal variation. nfstream sensor writing flow records to the store.

**Checkpoint:** 24h of captured benign flows, feature distributions plotted and
sane.

### Phase 2 — Detection and dashboard
Models trained on Phase 0 data, scoring live flows. Alerts in the store. Live
dashboard: traffic volume, alert stream, per-class breakdown, model version.

**Checkpoint — this is the demoable course deliverable.** An attack from the
attacker container appears on the dashboard within seconds.

### Phase 3 — The loop
Honeypots deployed. Log tailers extracting interaction events with cost
metadata. Labeler applying the auto-label policy. Retrainer with a versioned
model registry. Dashboard shows model history and per-version metrics.

**Checkpoint:** clean honeypot data measurably improves the deployed detector.
The honest loop works.

### Phase 4 — Attacks
A1 and A4 as live scenarios driven from the attacker container. Dashboard gains
a before/after view showing FPR climbing as A1 runs.

**Checkpoint:** the Phase 0 A1 result reproduces in the live system. Any
divergence is itself a finding — investigate, don't paper over it.

### Phase 5 — Defenses
D1 first; formalize the cost function before implementing it or it will read as
a heuristic. Then D2. A2 and D3 if time allows.

**Checkpoint:** A1 defeated by D1, with a measured increase in required attacker
cost. Ablation table complete.

### Phase 6 — Writeup
Figures regenerated from scratch via `make figures`. Artifact packaged for
release — in this subfield an artifact is close to mandatory for a serious venue.

---

## How I want you to work

- **One phase at a time.** Do not scaffold future phases. Stop at each
  checkpoint and report what you found.
- **Report negative results immediately.** If A1 does not move FPR, or the clean
  loop does not improve the detector, that is the most important information in
  the project. Tell me rather than tuning until it looks right.
- **Flag methodological problems.** If part of this design is unsound, say so.
  I would rather hear it from you than from a reviewer.
- Prefer boring, inspectable implementations over clever ones. This code has to
  survive being read by a reviewer.
- When a decision is genuinely ambiguous, ask instead of guessing.
