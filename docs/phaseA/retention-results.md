# Phase A item C — retention: sliding window vs. accumulate (results)

Pre-registration: `docs/DECISIONS.md` §29.C. Run exactly as specified there; nothing below
changes a cell, a seed count, a test, or the bar.

## What was run

CICIDS2017 (original `MachineLearningCVE` release, from `harshitchhabi/IDS-data`), tau = 0.1, RF,
jitter 0, ratios {0.2, 0.5}, 15 seeds, 20 rounds, `budget_mode = fixed_ratio` (the runner's
default, and what the §29.C commands use), `--no-fidelity`. Three invocations of
`experiments/phase0_loop.py`, one per retention setting, all into `results/phaseA/retention/`
(nothing read from or written to `results/phase0/loop/cicids_recal/`):

| setting | log | config | jobs |
|---|---|---|---|
| `accumulate` | `run_accumulate.log` | `config_control_a1_1abda4dafe63a00c.json` | 45/45 |
| `sliding_window`, `window_rounds=5` | `run_w5.log` | `config_control_a1_3895fa0fb07bb15e.json` | 45/45 |
| `sliding_window`, `window_rounds=10` | `run_w10.log` | `config_control_a1_853ad20fb799b11c.json` | 45/45 |

The loop dataset built from the raw CSVs (`experiments/phase0_loop_data.py --source cicids`)
matches the paper's run exactly on every recorded count: seed 30,000 rows, eval 52,337 rows, arm
counts seen_both/seed_only/honeypot_only = 4,337/4,000/4,000. The CICIDS smoke check
(`--window 5`, 1 seed, 2 rounds) ran clean before the real runs.

Environment note: the VM had **1 vCPU** (not 4 as `common.md` §3 assumes) and 15 GB RAM.
`--workers 3` was kept as specified; each 45-job invocation took ~20-23 minutes. No errors, no OOM.

Statistics: `experiments/phaseA_retention_stats.py`, which imports `paired_deltas`,
`paired_permutation_p` and `report_cell` from `experiments/phase0_stats_recompute.py` unchanged
(paired $t$; Monte Carlo sign-flip permutation, 10,000 resamples since $n = 15 > 12$; 95% $t$ CI).
Each cell is A1 final-round (round 20) fixed-threshold FPR minus the same seed's control
final-round fixed-threshold FPR, **with the control run under the same retention setting**. The
job CSVs record `retention` but not the window size, so the setting is read from the job-file
name's LoopConfig tag (`_w5_fr` / `_w10_fr` / none), and the script asserts that the tag and
the recorded `retention` column agree. Holm-Bonferroni step-down, family of 6, $\alpha = 0.05$, on
$p_t$ (the primary test, as in §26.1/§26.8), applied separately to $p_{\rm perm}$ as well. "Same
direction as accumulate" means $\Delta$FPR > 0. Per-cell output:
`results/phaseA/retention/retention_stats.csv`.

## Methodological caveat: read this before the table

**Under `budget_mode = fixed_ratio`, retention cannot change the final-round poison share, by
construction.** `LoopConfig.budgets()` sizes the adversary's per-round batch so the honeypot
share reaches `poison_ratio` *by the final round* under `accumulate` and *once the window is
full* under `sliding_window`. So the sliding-window adversary sends a larger batch each round:
at ratio 0.2 it sends 375 rows/round under accumulate, 750 under w=10 and 1,500 under w=5. At
round 20 every setting trains on exactly 7,500 honeypot rows out of 37,500 (30,000 out of 60,000
at ratio 0.5). The table below therefore compares three training sets with the **same honeypot
share and the same label conflict**, which differ only in how recently the poison arrived. It
does not test the scenario §29.C's hypothesis has in mind ("honeypot influence never ages out"
vs. old poison being dropped). That would need a constant attacker budget, `budget_mode =
fixed_batch`, where the windowed share plateaus below the accumulated one.

This follows from documented behaviour in `src/dloop/loop/config.py` (module docstring,
"`fixed_ratio` sizes per-round batches so the honeypot share of the training set reaches
`poison_ratio` by the final round (`accumulate`) or once the window is full
(`sliding_window`)"), and it was visible in the per-round `n_honeypot` column. The pre-registration did not flag it.
Per `common.md` §1, the runs were **not** changed: they are exactly the pre-registered
commands, and the disagreement is recorded here instead. One reading is defensible on its own
terms: the labelling policy is public, so an adversary who knows the window can send more per
round to hold its share. Under that reading the result says "a sliding window is no defense
against an adversary who can scale its per-round volume". It does not say that slow poisoning
ages out. The `fixed_batch` comparison is an obvious follow-up, but it is **not** pre-registered
and was not run.

Descriptive support (not hypothesis-tested; mean over 15 seeds, A1 fixed-threshold FPR by round):

| round | acc r=0.2 | w10 r=0.2 | w5 r=0.2 | acc r=0.5 | w10 r=0.5 | w5 r=0.5 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.007 | 0.011 | 0.020 | 0.020 | 0.092 | 0.414 |
| 3 | 0.014 | 0.046 | 0.250 | 0.250 | 0.620 | 0.840 |
| 5 | 0.034 | 0.167 | 0.535 | 0.535 | 0.804 | 0.923 |
| 10 | 0.166 | 0.529 | 0.534 | 0.803 | 0.918 | 0.920 |
| 20 | 0.533 | 0.541 | 0.534 | 0.920 | 0.923 | 0.921 |

FPR tracks the honeypot share at each round. A sliding window reaches the full damage *sooner*
(at round 5 for w=5, round 10 for w=10, round 20 for accumulate), then holds it, and does not
lower it. Controls carry no honeypot data, so their per-round FPR is identical across the three
settings (verified row by row, final-round mean 0.0045).

## Results

| cell | n | effect ($\Delta$FPR, fixed) | 95% CI | $t$ | $p_t$ | $p_{\rm perm}$ | vs. §29 bar |
|---|---|---|---|---|---|---|---|
| accumulate, ratio 0.2 | 15 | +0.528 | [+0.398, +0.658] | 8.72 | 5.0e-07 | <0.0001 | clears Holm (rank 5, thr 0.0250), both tests |
| accumulate, ratio 0.5 | 15 | +0.916 | [+0.883, +0.949] | 59.18 | 3.3e-18 | <0.0001 | clears Holm (rank 3, thr 0.0125), both tests |
| sliding_window w=5, ratio 0.2 | 15 | +0.530 | [+0.396, +0.664] | 8.50 | 6.7e-07 | <0.0001 | clears Holm (rank 6, thr 0.0500), both tests |
| sliding_window w=5, ratio 0.5 | 15 | +0.917 | [+0.884, +0.949] | 60.46 | 2.5e-18 | <0.0001 | clears Holm (rank 2, thr 0.0100), both tests |
| sliding_window w=10, ratio 0.2 | 15 | +0.536 | [+0.405, +0.667] | 8.77 | 4.6e-07 | <0.0001 | clears Holm (rank 4, thr 0.0167), both tests |
| sliding_window w=10, ratio 0.5 | 15 | +0.919 | [+0.887, +0.951] | 61.91 | 1.8e-18 | <0.0001 | clears Holm (rank 1, thr 0.0083), both tests |

Holm ranks and thresholds are from $p_t$. $p_{\rm perm}$ is a Monte Carlo count of 0 in 10,000
resamples for every cell, so the true value is below the resolution, not 0. That is below every Holm threshold in
the family, so each cell clears Holm by the permutation test as well. All six effects are positive (same direction as
`accumulate`).

**Verdict: replicated.** §29.C's bar: "**Replicates** (damage is retention-policy-independent)
iff all 6 cells clear the family's Holm threshold, same direction as `accumulate`." All 6 cells
clear Holm by both the paired $t$ and the permutation test, and all are positive. At the final
round, the three settings' effects are within 0.01 of each other at each ratio. This verdict holds
**for the pre-registered `fixed_ratio` budget**, where (see the caveat above) retention leaves
the final-round poison share unchanged by construction. It shows that A1's damage does not need
poison to accumulate over many rounds: the most recent `window_rounds` of honeypot data,
at the same share, does the same harm. It does **not** show that a sliding window fails against
a constant-volume adversary whose share would shrink under the window. That question was not
pre-registered and was not run.

---

## C2 — retention under a constant attacker budget

Pre-registration: `docs/phaseA/retention-c2-prereg.md`, committed and pushed on its own
(85e9933, 2026-10-06T06:41:22Z) before any C2 run, including the smoke test. Run exactly as
pre-registered: CICIDS2017, tau 0.1, RF, A1 jitter 0, 15 seeds, 20 rounds,
`--budget-mode fixed_batch`, batch 375 / 1500 rows/round, retention accumulate / w=5 / w=10,
6 invocations into `results/phaseA/retention-c2/`. All 180 jobs completed with exit 0.
Stats: `experiments/phaseA_retention_c2_stats.py`, which imports `paired_deltas` /
`report_cell` from `phase0_stats_recompute` unchanged and reuses item C's `holm`. Per-cell
output: `results/phaseA/retention-c2/retention_c2_stats.csv`.

| setting | log | config |
|---|---|---|
| accumulate, b375 | `run_acc_b375.log` | `config_control_a1_d68682940b9ad01c.json` |
| w=5, b375 | `run_w5_b375.log` | `config_control_a1_eb9c75360b580f8b.json` |
| w=10, b375 | `run_w10_b375.log` | `config_control_a1_d8d0f1999f37a91e.json` |
| accumulate, b1500 | `run_acc_b1500.log` | `config_control_a1_dc959db186b2ef57.json` |
| w=5, b1500 | `run_w5_b1500.log` | `config_control_a1_d5f5c221080c1581.json` |
| w=10, b1500 | `run_w10_b1500.log` | `config_control_a1_c92b2b87362c5199.json` |

**Erratum to the pre-registration's job count (no design change):** the prereg says each
invocation runs "45 jobs: 15 control and 15 seeds × 1 A1 cell". That is 30 jobs, not 45
(15 + 15), so the total is 180, not 270. The cells, seeds and commands are as written. The
pre-registration file was not edited.

### Pre-registered descriptive checks

- **Reproduction of item C: passed exactly.** All 30 `accumulate` b375 job files (15 A1 +
  15 control) are identical to item C's `accumulate` ratio 0.2 files in every round's
  `n_honeypot`, `n_train`, threshold, FPR, TPR and AUROC, and likewise b1500 vs. ratio 0.5
  (0 of 30 differ). An unplanned cross-check also matched: C2's w=5 b1500 cell is
  identical to item C's w=5 ratio 0.2 cell (+0.5298), as it should be, because both send
  1,500 rows/round into a 5-round window.
- **Controls:** per-round FPR identical across all 6 invocations (verified row by row).
- **Trajectories** (mean A1 fixed-threshold FPR over 15 seeds; honeypot rows retained at round
  20 and their share in brackets):

| round | acc b375 | w10 b375 | w5 b375 | acc b1500 | w10 b1500 | w5 b1500 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.007 | 0.007 | 0.007 | 0.020 | 0.020 | 0.020 |
| 5 | 0.034 | 0.034 | 0.034 | 0.535 | 0.535 | 0.535 |
| 8 | 0.093 | 0.093 | 0.032 | 0.732 | 0.732 | 0.537 |
| 10 | 0.166 | 0.166 | 0.033 | 0.803 | 0.803 | 0.534 |
| 15 | 0.373 | 0.164 | 0.030 | 0.884 | 0.801 | 0.530 |
| 20 | 0.533 | 0.161 | 0.031 | 0.920 | 0.799 | 0.534 |
| retained @20 | 7,500 (0.20) | 3,750 (0.11) | 1,875 (0.06) | 30,000 (0.50) | 15,000 (0.33) | 7,500 (0.20) |

The settings are identical until the window fills (round 5 for w=5, round 10 for w=10). After
that, damage stops growing and holds at that level, while under accumulate it keeps climbing.

### Family C2.1 — damage (A1 minus same-seed control, final-round fixed-threshold FPR; Holm within 6)

| cell | n | effect | 95% CI | $t$ | $p_t$ | $p_{\rm perm}$ | Holm (on $p_t$) |
|---|---|---|---|---|---|---|---|
| accumulate, b375 | 15 | +0.528 | [+0.398, +0.658] | 8.72 | 5.0e-07 | <0.0001 | clears (rank 3, thr 0.0125) |
| w=5, b375 | 15 | +0.027 | [+0.016, +0.037] | 5.42 | 9.0e-05 | <0.0001 | clears (rank 5, thr 0.0250) |
| w=10, b375 | 15 | +0.157 | [+0.082, +0.231] | 4.51 | 4.9e-04 | <0.0001 | clears (rank 6, thr 0.0500) |
| accumulate, b1500 | 15 | +0.916 | [+0.883, +0.949] | 59.18 | 3.3e-18 | <0.0001 | clears (rank 1, thr 0.0083) |
| w=5, b1500 | 15 | +0.530 | [+0.396, +0.664] | 8.50 | 6.7e-07 | <0.0001 | clears (rank 4, thr 0.0167) |
| w=10, b1500 | 15 | +0.795 | [+0.740, +0.850] | 30.84 | 2.8e-14 | <0.0001 | clears (rank 2, thr 0.0100) |

All 6 are positive and clear Holm by both tests. Windowing does not remove A1's damage in any
cell. The smallest effect (w=5, b375, +0.027) is still a statistically clear FPR increase over a
0.0045 control baseline, about 7×.

### Family C2.2 — does windowing reduce damage? (windowed ΔFPR minus accumulate ΔFPR, same seed and batch; Holm within 4)

| cell | n | effect | 95% CI | $t$ | $p_t$ | $p_{\rm perm}$ | vs. bar |
|---|---|---|---|---|---|---|---|
| w=5 − acc, b375 | 15 | −0.501 | [−0.623, −0.380] | −8.83 | 4.3e-07 | <0.0001 | **windowing reduces damage** (rank 3, thr 0.0250; perm clears too) |
| w=10 − acc, b375 | 15 | −0.371 | [−0.456, −0.287] | −9.42 | 1.9e-07 | <0.0001 | **windowing reduces damage** (rank 2, thr 0.0167; perm clears too) |
| w=5 − acc, b1500 | 15 | −0.386 | [−0.488, −0.284] | −8.10 | 1.2e-06 | <0.0001 | **windowing reduces damage** (rank 4, thr 0.0500; perm clears too) |
| w=10 − acc, b1500 | 15 | −0.121 | [−0.145, −0.097] | −10.67 | 4.2e-08 | <0.0001 | **windowing reduces damage** (rank 1, thr 0.0125; perm clears too) |

$p_{\rm perm}$ is a Monte Carlo count of 0 in 10,000 resamples for every cell (true $p$ below
1e-4, not 0).

**Verdict, per cell, against the pre-registered bar** ("windowing reduces damage" for a cell iff
its C2.2 contrast is negative and clears Holm, paired $t$ primary): **all 4 cells pass.**
w=5 and w=10 both reduce A1's final-round fixed-threshold FPR damage relative to accumulate, at
both 375 and 1,500 rows/round. The paired $t$ and the permutation test agree in every cell.

### Reading C and C2 together

- **Windowing reduces damage by capping retained poison; it does not remove it.** In every
  setting the damage matches the honeypot share retained at round 20 (C2.1, and the
  trajectory table). The share shrinks as w × B / (30,000 + w × B), and the damage shrinks with
  it. C2.1 shows damage still clearly present in all four windowed cells.
- **The reduction holds only against an attacker who does not adapt its volume.** Item C is the
  adaptive case: an attacker who knows the window size (and the labelling policy is public)
  sends 20/w times more per round and gets the accumulate-level damage back. Compare w=5 at
  1,500 rows/round (+0.530) with accumulate at 375 rows/round (+0.528). What windowing buys the
  defender is **attacker cost**: same damage for 30,000 total flows over 20 rounds instead of
  7,500 (4× under w=5, 2× under w=10). This total-flow cost comparison is descriptive and was not
  pre-registered.
- Limitations: one model (RF), one dataset, jitter 0, fixed threshold, final round only. The
  recalibrated threshold mode is in the job CSVs but was not part of either pre-registered
  family and is not reported here.
