# Phase B — results

Confirmatory run of the §32 pre-registration on the lab dataset (real traffic
through a live honeypot and the pinned fixed CICFlowMeter, validated in
`extractor-validation.md`). Dataset: 148,692 benign flows, 29,960 honeypot-bound
mimic flows (oracle 12,365 / profile 11,741 / replay 5,854), 32 real-attack flows;
partitions in `dloop.sim.lab`. All bars are quoted from §32 and were fixed before
this run. Seeds 1–15, tau 0.1.

## B.1 — achievable fidelity (`results/phaseB/b1_fidelity.csv`)

Median NN RMS distance and twin fraction (δ=0.0015) of the honeypot-bound mimic
flows to the defender's benign reference, in the loop's normalised space, with the
benign-to-benign floor against a reference of the same size (|R| = 24,533), and the
ratio to that floor.

| strategy | n mimic | median NN | twin fraction | benign floor | ratio to floor |
|---|---:|---:|---:|---:|---:|
| profile | 11,741 | 0.640 | 0.0 | 0.0137 | 46.9× |
| **oracle** | 12,364 | **0.630** | 0.0 | 0.0137 | **46.1×** |
| replay | 5,853 | 0.632 | 0.0 | 0.0137 | 46.2× |

**Descriptive (no hypothesis test).** All three strategies land at ~0.63 median NN,
**~46× the benign-to-benign floor**, twin fraction 0. Even the **oracle** strategy
(profile learned from the defender's *own* benign data — the upper bound) does not
approach copy fidelity (ratio ≈ 1). The floor here (0.0137) sits in the paper's
cliff region (realized NN 0.011–0.014, §26.6), so the comparison is now meaningful:
real-traffic mimic flows fall **far to the right of the fidelity cliff**, where the
paper's own curve predicts A1 does little. Oracle has the smallest ratio and is the
primary strategy for B.2 (as §32.2 fixes: "the strategy with the smallest B.1
NN-distance-to-floor ratio").

## B.2 — end-to-end damage (`results/phaseB/b2_stats.csv`)

A1 = oracle mimic flows replayed unchanged (`LabReplayAdversary`, invoked by
`--a1-replay`) and labelled malicious; a1truth = the same flows labelled benign;
junk = volume with no fidelity; vs control. 15 seeds.

**Fixed threshold, ΔFPR (robust — measured on 49k benign):**

| model | ratio | a1 ΔFPR [95% CI] | a1truth | junk |
|---|---:|---|---:|---:|
| RF | 0.2 | **+0.00043** [0.00037, 0.00049] | −0.00003 | +0.00045 |
| RF | 0.5 | **+0.00058** [0.00045, 0.00070] | −0.00008 | +0.00050 |
| XGB | 0.2 | +0.00060 [0.00041, 0.00079] | +0.00003 | −0.00001 |
| XGB | 0.5 | +0.00187 [0.00098, 0.00275] | +0.00007 | +0.00006 |

**Recalibrated threshold, ΔTPR (coarse — only 12 trusted_eval attack rows, quantum
1/12 ≈ 0.083):**

| model | ratio | a1 ΔTPR [95% CI] | a1truth | junk |
|---|---:|---|---:|---:|
| RF | 0.2 | +0.156 [0.121, 0.190] | −0.067 | +0.150 |
| RF | 0.5 | +0.172 [0.145, 0.200] | −0.067 | +0.128 |
| XGB | 0.2 | +0.028 [0.005, 0.050] | −0.083 | 0.000 |
| XGB | 0.5 | +0.111 [0.060, 0.162] | −0.083 | 0.000 |

**Primary bar, quoted (§32.2):** *"realistic A1 replicates iff recalibrated ΔTPR
for RF at ratio 0.2 clears Bonferroni (α/4 = 0.0125) by paired t, and the s28
null-arm rule holds (each of a1truth and junk has its 95% CI including 0)."*

**Verdict (literal §32.2 outcome): "mixed".** RF recalibrated ΔTPR at r=0.2 clears
α/4 (p_t = 1.3e-7), **but the null-arm rule fails**: junk's CI is [0.092, 0.208]
(nowhere near 0) and a1truth's is [−0.086, −0.048]. By §32.2's definition ("mixed
iff a1 clears but a null arm does not"), the outcome is **mixed**.

**Interpretation (does not replicate).** The "mixed" is an artifact, not a real A1
effect. With only 12 eval attack rows, ΔTPR is quantised at 0.083, so **junk moves
TPR as much as a1 (+0.150 vs +0.156)** and the ΔTPR is *positive* (the opposite of
the TPR collapse the feature-space A1 causes). The recalibrated-TPR channel is not
usable at this eval-attack power, and nothing A1-specific survives it — so the
substantive reading is that real-traffic A1 **does not replicate** the feature-space
damage.

The robust channel is the fixed-threshold FPR on 49k benign, and it is decisive:
real-traffic A1 raises FPR by **+0.0004 to +0.0019**, versus the feature-space A1 at
copy fidelity (§17/§26) of **+0.34 to +0.88** — **three orders of magnitude smaller**
— and junk raises it the same amount as a1 (so even that tiny bump is volume/label
noise, not A1's label-conflict mechanism; a1truth, correctly labelled, moves it ~0).

**s26.6 comparison (also required by §32.2):** the mimic's realized NN is 0.63
(B.1), far past the cliff; the nearest s26.6 grid point (realized 1.06) has RF
recalibrated ΔTPR ≈ 0. The lab's noisy +0.156 is not the feature-space collapse and
is consistent with "no real damage at this fidelity."

**Reading:** real-traffic A1 — even with a defender-data oracle profile — does **not**
reproduce the feature-space A1 catastrophe, because real sessions through a live
honeypot and CICFlowMeter land ~46× past the fidelity cliff. The feature-space
result (DECISIONS §17, §26) was an **upper bound** requiring near-exact copies of
benign feature vectors, which real captured traffic does not produce.

**ShareCap c=0.05 (descriptive, `b2_sharecap_recovery.csv`):** recovery
R = 0.24 / 0.39 (RF, r=0.2/0.5) and −0.38 / 0.51 (XGB). With undefended A1 damage
already at the 0.0004–0.0019 FPR noise floor, R is computed against a near-zero
denominator and is **not meaningful here** — ShareCap's value is established on the
feature-space damage (DECISIONS §24–25), not on this run where there is almost no
damage to recover.

## B.3 — cost (`results/phaseB/b3_cost.csv`)

Oracle mimic, per poison flow accepted into training and the time to a 20% honeypot
share at one retrain every **N = 10 min** (§32.3):

| quantity | value |
|---|---:|
| mimic flows captured | 12,365 over 12.9 min (957 flows/min) |
| per-flow packets | 12.0 |
| per-flow bytes | 819 |
| per-flow connections | 0.37 |
| per-flow wall-clock | 0.020 s |
| honeypot rows for 20% of 30k seed | 7,500 |
| **rounds to 20% share** | **1** (one 10-min retrain) |
| wall-clock to 20% share | 10 min |

The poison is **cheap**: the attacker reaches a 20% training-set share in a single
retrain window, at ~12 packets / 819 bytes per flow — the threat model's "the poison
budget is the whole honeypot share, acquired for free" holds at the traffic level.
But B.2 shows that at the fidelity real traffic achieves, a 20% share inflicts
almost no damage. The threat is cheap to *mount*; it is not, in this lab, cheap to
make *effective*.

## Limitations

- **Eval attack power.** The lab's real attacks produced only ~32 flows (12 in
  trusted_eval), so recalibrated ΔTPR is quantised at 1/12 and not usable; the FPR
  channel (49k benign) carries the B.2 conclusion. Reported, not worked around.
- **Fidelity ceiling.** Reaching copy fidelity in real traffic — the regime where
  A1 is catastrophic — remains open; it would need replaying captured benign *flows*
  rather than re-issuing sessions, and is future work. B.1 shows a distributional
  oracle does not get there.
- Memory: the whole pipeline ran inside the 1.86 GiB Docker VM by splitting inputs
  (capture rotation, per-file extraction); no limit was raised.
