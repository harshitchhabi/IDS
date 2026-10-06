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
