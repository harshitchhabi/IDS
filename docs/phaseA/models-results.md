# Phase A, item A — models results (logreg, MLP)

Pre-registration: `docs/DECISIONS.md` §29.A (unchanged). Session instructions:
`docs/phaseA/session-models.md`, `docs/phaseA/common.md`.

## What was run

| run | scenarios | jobs | config hash | log |
|---|---|---|---|---|
| damage | control, a1 × jitter {0, 0.7} × ratio {0.2, 0.5} | 150 | `9f5173f51ba0706c` | `results/phaseA/models/run_damage.log` |
| mech 1 | a1truth, s0j @ jitter 0.7, ratio 0.2 | 60 | `d3dfcdc01d399f65` | `results/phaseA/models/run_mech1.log` |
| mech 2 | junk @ jitter 0, ratio 0.2 | 30 | `695e12eebd1eb466` | `results/phaseA/models/run_mech2.log` |

All three commands were run exactly as written in `session-models.md` (CICIDS2017,
`--val-nn-tau 0.1`, models `logreg mlp`, seeds 1–15, 20 rounds, `--workers 3`, `--no-fidelity`).
None of them logged an error. Per-seed job CSVs are in `results/phaseA/models/jobs/` (240 files).
Statistics come from `experiments/phaseA_models_stats.py`. That script imports `paired_deltas` and
`report_cell` from `experiments/phase0_stats_recompute.py` unchanged. It uses the same final-round,
same-seed delta against control and the same paired t-test and paired permutation test (Monte Carlo
with 10,000 resamples, since n = 15 > 12). Full output is in `results/phaseA/models/stats.csv`.

**Correction convention.** §29.A says "clear the family's Holm threshold" for A.1 without naming the
test. I applied Holm to the paired-t p, the project's primary test under the s27 convention
("t-test + Holm, within each family's own pre-specified bar"; the permutation test is "reported for
transparency rather than as the primary significance claim"). I also applied Holm separately to the
permutation p. The table shows both. The verdicts below use the t-test, with the permutation-test
outcome noted wherever it would change the verdict. A.2 states its own rule ("by **both** tests"),
and I applied it as written.

### Environment and deviations from the session file

- Python 3.12 (`uv sync --group dev`). torch 2.14.0 is the plain PyPI wheel, because
  download.pytorch.org is blocked by this environment's egress proxy. Other versions:
  scikit-learn 1.9.0, xgboost 3.4.1, numpy 2.5.2.
- Data: `harshitchhabi/IDS-data` @ `06f5d926`, `cicids2017/` only, extracted into
  `data/cicids2017/` (8 CSVs).
- **A step missing from the session file.** `experiments/phase0_loop.py` loads
  `data/loop/cicids.npz`, a gitignored derived cache that a fresh clone does not have. The first
  smoke-test attempt failed with `FileNotFoundError` on it. With the user's approval I built it with
  the project's own builder, `python -m experiments.phase0_loop_data --source cicids`, unmodified.
  The builder uses the within-day temporal partition, near-duplicate grid 0.005, the DDoS/Hulk arms
  and `leak_warning: true`. Its counts (seed 30,000; pool benign 344,227; pool attack 130,166;
  eval 52,337) match the counts in `results/phase0/cicids/partition_summary.csv`. After that the
  CICIDS smoke test passed: 4 job files in 0.7 min. `session-models.md` / `common.md` §2 should list
  this step.
- Work was committed to `claude/practical-meitner-2qsk9a` rather than `phase-a-models`, at the
  user's instruction. That branch is the only one this cloud session may push to.

## Context needed to read the numbers

Both new models are much **weaker detectors** than RF/XGBoost on this partition. Each figure is the
control's mean final-round recalibrated TPR (1% FPR on calibration benign) over 15 seeds:

| model | round-0 TPR | final TPR | final AUROC |
|---|---|---|---|
| RF (s26/s28 runs, `cicids_recal`, 15 seeds) | 0.828 | 0.826 | 0.965 |
| XGBoost (`cicids_recal`, 5 seeds) | 0.821 | 0.811 | 0.982 |
| logreg | 0.434 | 0.435 | 0.954 |
| MLP | 0.364 | 0.392 | 0.893 |

This matters for family A.2 (see "Disagreement with the bar" below). The `val_benign_dropped_frac`
from τ = 0.1 calibration (~0.93–0.94) is the same for the new models as for the published RF runs,
so calibration behaves identically.

## Results

ΔFPR is measured at the fixed threshold and ΔTPR at the recalibrated threshold. Each is the
final-round A1 (or null-arm) value minus the same-seed control value. "Holm thr" is the cell's own
step-down threshold at α = 0.05 within its model's 8-cell family. Thresholds differ between the t
and permutation columns because the two tests rank the cells differently. A ✓ means the test
clears the threshold.

| cell | n | effect | 95% CI | $t$ | $p_t$ | $p_{\rm perm}$ | vs. §29 bar |
|---|---|---|---|---|---|---|---|
| A.1/logreg fixed ΔFPR r=0.2 j=0 | 15 | +0.0002 | [+0.0000, +0.0004] | 2.32 | 0.036 | 0.0005 | Holm thr 0.025: t ✗ / perm ✓ (thr 0.0125) |
| A.1/logreg fixed ΔFPR r=0.2 j=0.7 | 15 | +0.0053 | [+0.0005, +0.0102] | 2.36 | 0.033 | 0.0005 | Holm thr 0.0167: t ✗ / perm ✓ (thr 0.0167) |
| A.1/logreg fixed ΔFPR r=0.5 j=0 | 15 | +0.0326 | [−0.0160, +0.0812] | 1.44 | 0.17 | 0.0023 | Holm thr 0.05: t ✗ / perm ✓ (thr 0.05) |
| A.1/logreg fixed ΔFPR r=0.5 j=0.7 | 15 | +0.0182 | [+0.0061, +0.0304] | 3.21 | 0.0063 | 0.0013 | Holm thr 0.0125: t ✓ / perm ✓ (thr 0.025) |
| A.1/logreg recal ΔTPR r=0.2 j=0 | 15 | −0.0968 | [−0.1043, −0.0893] | −27.67 | 1.3e-13 | <0.0001 | Holm thr 0.01: t ✓ / perm ✓ (thr 0.00625) |
| A.1/logreg recal ΔTPR r=0.2 j=0.7 | 15 | −0.1543 | [−0.1618, −0.1468] | −44.11 | 2.0e-16 | <0.0001 | Holm thr 0.00833: t ✓ / perm ✓ (thr 0.00714) |
| A.1/logreg recal ΔTPR r=0.5 j=0 | 15 | −0.1531 | [−0.1602, −0.1461] | −46.69 | 9.0e-17 | <0.0001 | Holm thr 0.00714: t ✓ / perm ✓ (thr 0.00833) |
| A.1/logreg recal ΔTPR r=0.5 j=0.7 | 15 | −0.4232 | [−0.4302, −0.4162] | −129.09 | 6.2e-23 | <0.0001 | Holm thr 0.00625: t ✓ / perm ✓ (thr 0.01) |
| A.1/mlp fixed ΔFPR r=0.2 j=0 | 15 | +0.0017 | [−0.0000, +0.0034] | 2.08 | 0.056 | 0.0001 | Holm thr 0.0167: t ✗ / perm ✓ (thr 0.0125) |
| A.1/mlp fixed ΔFPR r=0.2 j=0.7 | 15 | +0.0099 | [+0.0043, +0.0154] | 3.81 | 0.0019 | <0.0001 | Holm thr 0.00833: t ✓ / perm ✓ (thr 0.00625) |
| A.1/mlp fixed ΔFPR r=0.5 j=0 | 15 | +0.4089 | [+0.2350, +0.5828] | 5.04 | 0.00018 | <0.0001 | Holm thr 0.00625: t ✓ / perm ✓ (thr 0.00714) |
| A.1/mlp fixed ΔFPR r=0.5 j=0.7 | 15 | +0.1141 | [+0.0301, +0.1981] | 2.91 | 0.011 | <0.0001 | Holm thr 0.01: t ✗ / perm ✓ (thr 0.00833) |
| A.1/mlp recal ΔTPR r=0.2 j=0 | 15 | +0.0564 | [+0.0310, +0.0818] | 4.76 | 0.00031 | <0.0001 | Holm thr 0.00714: t ✓ / perm ✓ (thr 0.01) — **positive** (TPR rises) |
| A.1/mlp recal ΔTPR r=0.2 j=0.7 | 15 | +0.0239 | [−0.0001, +0.0478] | 2.14 | 0.050 | 0.0403 | Holm thr 0.0125: t ✗ / perm ✗ (thr 0.0167) |
| A.1/mlp recal ΔTPR r=0.5 j=0 | 15 | +0.0042 | [−0.0227, +0.0311] | 0.34 | 0.74 | 0.738 | Holm thr 0.05: t ✗ / perm ✗ (thr 0.05) |
| A.1/mlp recal ΔTPR r=0.5 j=0.7 | 15 | −0.0166 | [−0.0626, +0.0294] | −0.77 | 0.45 | 0.449 | Holm thr 0.025: t ✗ / perm ✗ (thr 0.025) |
| A.2/logreg a1 recal ΔTPR r=0.2 j=0.7 | 15 | −0.1543 | [−0.1618, −0.1468] | −44.11 | 2.0e-16 | <0.0001 | α/4 = 0.0125: t ✓ / perm ✓ |
| A.2/logreg a1truth recal ΔTPR r=0.2 j=0.7 | 15 | +0.2295 | [+0.2228, +0.2363] | 73.07 | 1.8e-19 | <0.0001 | null arm: CI excludes 0 ✗ |
| A.2/logreg s0j recal ΔTPR r=0.2 j=0.7 | 15 | +0.0391 | [+0.0268, +0.0514] | 6.81 | 8.4e-06 | <0.0001 | null arm: CI excludes 0 ✗ |
| A.2/logreg junk recal ΔTPR r=0.2 j=0 | 15 | +0.1435 | [+0.1370, +0.1500] | 47.37 | 7.4e-17 | <0.0001 | null arm: CI excludes 0 ✗ |
| A.2/mlp a1 recal ΔTPR r=0.2 j=0.7 | 15 | +0.0239 | [−0.0001, +0.0478] | 2.14 | 0.050 | 0.0403 | α/4 = 0.0125: t ✗ / perm ✗ |
| A.2/mlp a1truth recal ΔTPR r=0.2 j=0.7 | 15 | −0.0330 | [−0.0628, −0.0031] | −2.37 | 0.033 | 0.0353 | null arm: CI excludes 0 ✗ |
| A.2/mlp s0j recal ΔTPR r=0.2 j=0.7 | 15 | +0.0694 | [+0.0384, +0.1005] | 4.80 | 0.00028 | 0.0002 | null arm: CI excludes 0 ✗ |
| A.2/mlp junk recal ΔTPR r=0.2 j=0 | 15 | +0.0619 | [+0.0313, +0.0925] | 4.34 | 0.00068 | <0.0001 | null arm: CI excludes 0 ✗ |

(The A.2 `a1` rows repeat the A.1 jitter-0.7 / ratio-0.2 recalibrated cells, computed from the same
job files without rerunning them, per §29.A.)

## Verdicts against the §29.A bar

The bar, quoted: "**Replicates** iff (a) in family A.1, at least the jitter-0, fixed-threshold
$\Delta$FPR cells (both ratios) clear the family's Holm threshold, matching CICIDS2017
RF/XGBoost's own "damage needs copy-level fidelity" pattern, **and** (b) in family A.2, the `a1`
arm clears the family's Bonferroni threshold ($\alpha/4 = 0.0125$) by **both** tests **and** every
null arm's 95% CI includes 0 (the exact s28 bar, applied to this model). **Does not replicate**
iff neither (a) nor (b) is met. **Mixed** iff exactly one of (a), (b) is met, or if (a) is met for
one ratio but not the other."

**Logistic regression: did not replicate.**
- **(a) fails at both ratios** under the t-test with Holm:
  - Ratio 0.2, jitter 0: $p_t$ = 0.036 against a threshold of 0.025. The effect itself is
    +0.0002 FPR.
  - Ratio 0.5, jitter 0: $p_t$ = 0.17 against 0.05. Here the mean is +0.033, but one or two seeds
    carry it and the CI spans 0.
  - Under the permutation test both cells clear Holm ($p_{\rm perm}$ = 0.0005 and 0.0023). On the
    permutation reading (a) would be met and the verdict would be **mixed**. The two tests disagree
    because every per-seed delta is ≥ 0 and the tail is heavy. At ratio 0.5, seed 7 is +0.34 and
    seed 8 is +0.079, and the other 13 are below 0.04, five of them exactly 0. The sign-flip test
    reacts to the consistent sign, while the t-test is dominated by the tail's variance.
- **(b) fails.** The `a1` arm clears α/4 by both tests: ΔTPR −0.154, $p_t$ = 2e-16,
  $p_{\rm perm}$ < 0.0001. But **none** of the three null arms has a CI that includes 0. All three
  *raise* TPR: `a1truth` +0.230, `s0j` +0.039, `junk` +0.144.
- Outside the bar's conditions, the recalibrated-threshold TPR loss is large and very significant
  in all four A.1 cells. It runs from −0.097 to −0.423, so logreg's A1 damage shows up as lost
  detection at both fidelities, not as fixed-threshold FPR.

**MLP: mixed.**
- **(a) is met at ratio 0.5 only:**
  - Ratio 0.5, jitter 0 clears Holm: ΔFPR +0.409, $p_t$ = 0.00018 against a threshold of 0.00625.
  - Ratio 0.2, jitter 0 does not: ΔFPR +0.0017, $p_t$ = 0.056 against 0.0167.
  - This matches the bar's clause "(a) is met for one ratio but not the other". Under the
    permutation test ratio 0.2 also clears ($p_{\rm perm}$ = 0.0001), which would make (a) fully
    met. (b) still fails, so the verdict is **mixed** on either reading.
- **(b) fails on both counts.**
  - The `a1` arm does not clear α/4: $p_t$ = 0.050, $p_{\rm perm}$ = 0.040. Its point estimate is
    *positive* (+0.024 TPR).
  - No null arm's CI includes 0: `a1truth` −0.033, `s0j` +0.069, `junk` +0.062.
- At the recalibrated threshold, MLP's A1 never costs detection. The one significant recalibrated
  cell (ratio 0.2, jitter 0) *raises* TPR by +0.056. For this model A1's damage is fixed-threshold
  FPR (up to +0.41 at ratio 0.5), and recalibration removes it.

## Disagreement with the bar, and limitations

These are reported here, as `common.md` §1 requires, rather than by editing §29. Nothing was rerun.

1. **The null-arm condition assumes a saturated detector.** On RF (s28) the null arms leave TPR
   unchanged, because at TPR ≈ 0.83 adding data does not move the detector. Logreg (control TPR
   0.43) and the MLP (0.39) are far from saturation. *Any* extra training data — a1truth
   (correctly-labelled benign), s0j (correctly-labelled attacks), even junk — moves TPR by an amount
   that 15 seeds resolve easily. The condition "every null arm's 95% CI includes 0" therefore fails
   for a reason unrelated to the label-conflict mechanism.
   - For logreg the *direction* is what the mechanism predicts: only the mislabelled `a1` arm lowers
     TPR (−0.154), and every correctly-labelled or uninformative arm raises it.
   - That is a qualitative pattern, not the pre-registered bar. I report it as an observation and
     do not count it toward the verdict.
2. **Weak base detectors.** The two new models detect roughly half as well as RF/XGBoost on this
   partition (table above). The results show what A1 does to *these* models with the default
   hyperparameters in `src/dloop/models/{logreg,mlp}.py`. They do not show what it does to a
   logistic-regression or MLP detector tuned to RF-level TPR, and no tuning was attempted, per the
   pre-registration.
3. **Logreg recalibrated variance is mostly control variance.** Final-round recalibrated TPR for the
   logreg A1 arm has a per-seed SD of 0.0005–0.005, close to deterministic. The paired-delta SDs
   (0.013) come almost entirely from the control. The very large $t$ values (up to −129) reflect
   that, not 15 independently noisy measurements of the effect.
4. **Choice of test for (a).** For logreg, the A.1 verdict depends on which test is primary
   (t: did not replicate; permutation: mixed). §29.A does not say. I used the project's existing
   convention (t-test primary). §29.B/§29.C will probably hit the same ambiguity.
5. **Missing setup step** (the `data/loop/cicids.npz` build), described under "Environment and
   deviations" above.
