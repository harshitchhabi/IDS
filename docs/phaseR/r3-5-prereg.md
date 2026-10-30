# R3.5 pre-registration: onset below 0.01, and the S0 cost of a cap below it

Written and committed **before any R3.5 run** (the commit timestamp is the pre-registration). It is
the last R3 follow-up. It extends R3.4 (`docs/phaseR/r3-followup-prereg.md`; results in
`docs/phaseR/r3-results.md` §R3.4; branch `harshit/wonderful-hawking-g2q1ju`). DECISIONS.md is
not edited. Anything run differently from what is written here is reported as a deviation.

## Question

R3.4's onset rule failed on three pairs: NF-UNSW-NB15-v2/RF ($R_{0.005}$ = 0.835),
NF-ToN-IoT-v2/RF (0.554) and NF-ToN-IoT-v2/XGBoost (0.501). On all three the onset sat at the floor
of the grid (ratio 0.01). On those three pairs, R3.5 asks:

1. Is the damage onset below 0.01?
2. Does a cap below that onset recover the damage?
3. What does that cap cost in S0 gain?

## Pairs and fixed settings (same as R3 and R3.4, stated explicitly)

| pair | dataset | model | tau | grid |
|---|---|---|---|---|
| P1 | NF-UNSW-NB15-v2 | RF | **0.2, the §31.3 fallback** (no tau qualified; on this dataset numerically the same as no twin filter, R3's recorded limitation) | 0.005 |
| P2 | NF-ToN-IoT-v2 | RF | 0 | 0.005 |
| P3 | NF-ToN-IoT-v2 | XGBoost | 0 | 0.005 |

Tau and grid are R3's measured values, not re-derived. Seeds 1-15, 20 rounds, default (fixed) eval
subsample, `WORKERS=3`, `--no-fidelity`. Code is HEAD of this branch at the pre-registration
commit. Runs write to `results/phaseR/r3/<dataset>/`, so jobs that already exist are **reused,
not rerun**. That covers the control, A1 ratio 0.5 undefended and under $c\in$ {0.005, 0.01,
0.02, 0.05}, and S0 ratio 0.2 undefended, under those caps, and under uniform $w=0.05$. Paired
$t$ is primary (`phase0_stats_recompute.report_cell`), with the sign-flip permutation test
alongside. "Clears Holm" means rejected by **both** tests in the stated direction, as in R3 and
R3.4.

## Stage a: onset below 0.01

**Arms:** A1, no defense, jitter 0, ratios {0.001, 0.002, 0.005}, each pair, 15 seeds.

**Outcome:** fixed-threshold $\Delta$FPR, final round, A1 minus the same-seed control.

**Onset rule (R3.4's, applied to the new ratios):** Holm within the 3 new ratios per pair,
direction positive. Onset = the smallest of {0.001, 0.002, 0.005} that clears. If none clears,
the onset stays R3.4's measured 0.01. As a sensitivity check, not the rule, the onset is also
reported with Holm over all 7 ratios {0.001, ..., 0.10}, using R3.4's jobs for the upper four.

## Stage b: caps below the onset, and their S0 cost

**New arms:** A1 at ratio 0.5, jitter 0, under ShareCap $c\in$ {0.001, 0.002}; and S0 at ratio
0.2 under the same two caps. Each pair, 15 seeds.

**Recovery** $R_c$ is defined as in R3.3 / R3.4: $1 - \overline{\Delta\mathrm{FPR}}_c /
\overline{\Delta\mathrm{FPR}}_{\rm none}$, fixed threshold, final round, against the same-seed
control. A seed-bootstrap 95% CI is descriptive. Caps considered: {0.001, 0.002, 0.005, 0.01,
0.02, 0.05}. The last four are R3.4's.

**S0 gain** $g_c$ = S0 TPR minus the same-seed control TPR, fixed threshold, final round, all
attack rows. The control trains on no honeypot data at all, so it is the "S0 gain = 0" reference
the gain is tested against. $U_c = \overline g_c / \overline g_{\rm none}$ is reported as in R2.1
/ R3.4.

## Bars, per pair

**Onset rule (R3.4's bar, unchanged).** Let $c^*$ be the largest tested cap strictly below the
onset, from {0.001, 0.002, 0.005, 0.01, 0.02, 0.05}. That gives $c^*$ = 0.001 for onset 0.002;
0.002 for onset 0.005; 0.005 for onset 0.01 (R3.4's result, unchanged).

- **"The onset rule holds"** iff $R_{c^*}\ge0.90$.
- **"The onset rule does not hold"** iff $R_{c^*}<0.90$.
- **"No tested c is below the onset"** iff the onset is 0.001.
- **"Not evaluable"** iff R3.1's undefended ratio-0.5 jitter-0 $\Delta$FPR does not clear Holm.
  It clears on all three pairs (R3).

**S0 cost (additional report, per pair).** Family: $g_c$ for all six caps, tested against 0.
Holm within the 6 per pair, direction positive. Let $c_{90}$ be the **largest** cap with
$R_c\ge0.90$, the least restrictive cap that recovers. Report:

- **"The recovering cap keeps S0 gain"** iff $g_{c_{90}}$ clears Holm.
- **"The recovering cap keeps no significant S0 gain"** iff it does not.
- **"No tested cap recovers ≥ 90%"** iff no $c$ reaches $R_c\ge0.90$.

Every other cap that reaches $R_c\ge0.90$ is reported with its Holm status too.

## Named in advance

- **Pool-row reuse.** At ratio 0.5, NF-UNSW-NB15-v2 and NF-ToN-IoT-v2 already resample A1 batches
  (`batch_resampled`; R3.4). The new ratio-0.5 capped arms will too. Ratios 0.001-0.005 are not
  expected to. Every job's `batch_resampled` count is reported per arm.
- **Tiny honeypot batches.** At ratio 0.001 a round adds on the order of tens of honeypot rows,
  and at cap 0.001 their effective weight is far smaller still. Whatever the loop does at those
  sizes is reported, not avoided.
- **Within-sample choice.** As in R3.4, $c^*$ and $c_{90}$ are chosen on the same seeds that
  measure them.
- **Ratio vs. share.** As in R3.4, an unweighted onset ratio is compared to a cap on weighted
  share. That equivalence is what is being tested.

## Commands (run after this commit)

`experiments/run_phaseR_r3_5.sh <dataset> <tau> <models...>`, issuing exactly these
`experiments.phase0_loop` calls. Every call adds `--dataset <dataset> --val-nn-tau <tau> --models
<models> --seeds 15 --workers 3 --no-fidelity --out results/phaseR/r3/<dataset>`:

```
--scenarios control                                                    # reused
--scenarios a1 --jitters 0 --ratios 0.001 0.002 0.005                  # stage a
for c in 0.001 0.002:
  --scenarios a1 --jitters 0 --ratios 0.5 --defense sharecap --share-cap c
  --scenarios s0 --ratios 0.2 --defense sharecap --share-cap c
```

These are run as `nf-unsw-nb15-v2 0.2 rf` and `nf-ton-iot-v2 0 rf xgboost`: 315 new jobs in all
(stage a 135, stage-b A1 90, S0 90). A smoke test runs first (`SMOKE=1`, 1 seed, 2 rounds) into a
scratch root. Statistics are in `experiments/phaseR_r3_5_stats.py`, and the results are appended
to `docs/phaseR/r3-results.md` as "R3.5".
