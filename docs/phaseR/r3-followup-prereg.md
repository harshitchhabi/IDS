# R3.4 pre-registration: ShareCap with the cap set below the damage-onset share

Written and committed **before any R3.4 run** (the commit timestamp is the pre-registration).
It extends R3 (DECISIONS §31.3, results in `docs/phaseR/r3-results.md`, branch
`harshit/wonderful-hawking-g2q1ju`). DECISIONS.md is not edited. Anything run differently from
what is written here is reported as a deviation in the results, not fixed by editing this file.

## Question

Does ShareCap recover A1's damage once the cap $c$ is set below the dataset's damage-onset
share? R3.3 found $c=0.05$ recovers $R\ge0.90$ on NF-CSE-CIC-IDS2018-v2 but only 0.23-0.52 on
NF-UNSW-NB15-v2 and NF-ToN-IoT-v2. §25.5 says the right cap depends on where damage starts for a
given model and dataset. R3.4 measures where damage starts, then tests caps below that point.

## Fixed settings (same as R3, stated explicitly)

- **Datasets:** NF-UNSW-NB15-v2, NF-ToN-IoT-v2, and NF-CSE-CIC-IDS2018-v2 as the reference (the
  dataset where $c=0.05$ already held). Same subsamples, same loop caches, same code (HEAD of
  this branch at the pre-registration commit).
- **Grid:** 0.005 on all three (`experiments/_common.py` `NETFLOW_GRID`, the R3 §31.3 rule's
  outcome; not re-derived).
- **Tau** (§31.3's rule as R3 applied it; not re-derived):
  - NF-UNSW-NB15-v2: **tau = 0.2, the §31.3 fallback** ("If no tau qualifies, tau = 0.2"). R3
    recorded that on this dataset tau 0.2 is numerically the same as no twin filter, because of the
    < 100-row fallback in `BaseDetector._val_rows_without_twins`. Kept as is, so R3.4 stays
    comparable to R3.1/R3.3, and the same limitation applies.
  - NF-ToN-IoT-v2: tau = 0.
  - NF-CSE-CIC-IDS2018-v2: tau = 0.
- **Models:** RF and XGBoost. **Seeds:** 1-15. **Rounds:** 20 (default). Default (fixed) eval
  subsample. `WORKERS=3`, `--no-fidelity`, as in R3.
- **Reuse:** runs write to R3's own directory, `results/phaseR/r3/<dataset>/`. The runner skips
  any job whose CSV already exists, so the following R3 jobs (same code, same configs) are
  **reused, not rerun**: the control, A1 at ratio 0.5 jitter 0 with no defense (R3.1), and A1
  at ratio 0.5 under ShareCap $c=0.05$ (R3.3, "the existing 0.05").
- **Primary test:** paired $t$ (`experiments/phase0_stats_recompute.report_cell`); the
  sign-flip permutation test is reported alongside. "Clears Holm" means rejected by **both**
  tests in the stated direction, R3's reading.

## Stage a: damage onset

**Arms:** A1, no defense, jitter 0, ratios {0.01, 0.02, 0.05, 0.10}, RF and XGBoost, 15 seeds,
each dataset. The control is R3's.

**Outcome:** fixed-threshold $\Delta$FPR, final round, A1 minus same-seed control.

**Family:** the 4 ratios per (dataset, model). Holm within the 4, direction positive.

**Onset share** per (dataset, model): the smallest ratio in {0.01, 0.02, 0.05, 0.10} whose
$\Delta$FPR clears Holm (positive). Every ratio is reported whether or not it clears. If no ratio
up to 0.10 clears, the onset is recorded as "> 0.10".

## Stage b: caps below onset

**Arms:** A1 at ratio 0.5, jitter 0, under ShareCap $c\in$ {0.005, 0.01, 0.02} (new) and 0.05
(R3.3, reused). Same datasets, models and seeds. Retention arms, following R2.1: S0 at ratio 0.2
under no defense, ShareCap $c\in$ {0.005, 0.01, 0.02, 0.05}, and uniform $w=0.05$, both models.

**Recovery**, as R3.3 / R2.1 define it: $R_c = 1 - \overline{\Delta\mathrm{FPR}}_{c} /
\overline{\Delta\mathrm{FPR}}_{\rm none}$. A1, ratio 0.5, jitter 0, fixed threshold, final round,
means over the 15 seeds. Each $\Delta$FPR is against the same-seed control, and "none" is R3.1's
undefended A1 at the same seed. A seed-bootstrap 95% CI (10,000 resamples) is descriptive.

**Retention (S0 gain kept)**, as R2.1 defines it: $U_c = \overline{g}_c / \overline{g}_{\rm none}$,
with $g$ = S0 TPR minus same-seed control TPR, fixed threshold, final round. NetFlow v2 has no
withheld family, so $g$ is read on all attack rows (R2.1's rule for UNSW-NB15). If
$\overline{g}_{\rm none}$ is not positive with paired-$t$ $p<0.05$, $U$ is undefined for that
(dataset, model), and the retention comparison is reported as "not evaluable". $U_{\rm
uniform\,0.05}$ is computed the same way.

**Family (reported, not the bar):** defended minus undefended $\Delta$FPR at the same seed, for the
4 caps per (dataset, model). Holm within the 4, direction "defense lowers FPR".

## Bar, per (dataset, model)

Let $c^*$ be the **largest tested $c$ strictly below the measured onset share**. For onset 0.01,
0.02, 0.05, 0.10 and "> 0.10", $c^*$ is 0.005, 0.01, 0.02, 0.05 and 0.05.

- **"The onset rule holds"** iff $R_{c^*}\ge0.90$.
- **"The onset rule does not hold"** iff $R_{c^*}<0.90$.
- **"No tested c is below the onset"** iff no $c$ in {0.005, 0.01, 0.02, 0.05} is below the onset
  share. With these grids that can happen only if the onset is below 0.005, which stage a cannot
  measure, so this outcome is listed for completeness.
- **"Not evaluable"** iff the undefended A1 $\Delta$FPR at ratio 0.5 (R3.1's cell) does not
  clear Holm, i.e. there is no damage to recover. R3.1 found it clears on all six pairs.

Reported at $c^*$ next to the bar, never in place of it: $U_{c^*}$ against $U_{\rm uniform\,0.05}$
(and their difference, with a seed-bootstrap 95% CI), or "not evaluable" under the rule above.
$R_c$ and $U_c$ at every other cap are reported as a cap curve, with no bar.

## Cross-dataset reading, fixed now

The comparison of interest is whether NF-UNSW-NB15-v2 and NF-ToN-IoT-v2, where $c=0.05$ failed,
reach $R\ge0.90$ at their own $c^*$. NF-CSE-CIC-IDS2018-v2 is the reference: its onset and $c^*$
are reported the same way. If it holds at $c=0.05$ but its $c^*$ is smaller, the bar is
still read at $c^*$.

## Named in advance

- **Selection.** $c^*$ is chosen from the same seeds that are used to measure $R_{c^*}$ (the A1
  arms at ratio 0.5 are separate jobs from stage a's low-ratio arms, but the seeds and control
  are shared). This is a within-sample rule, not a held-out one, and is reported as such.
- **Onset uses ratio, ShareCap caps share.** ShareCap caps the *effective* weighted share, so a
  cap $c$ is compared to an onset measured as an unweighted poison ratio. They are treated as the
  same quantity here, which is the hypothesis being tested, not a fact.
- **Small-ratio batches.** Ratios 0.01-0.02 put only a few hundred honeypot rows into training.
  Whatever the loop does at those sizes (including any `batch_resampled` flag) is reported, not
  avoided.

## Commands (run after this commit)

A new runner, `experiments/run_phaseR_r3_4.sh <dataset> <tau>`, that issues exactly these
`experiments.phase0_loop` calls. The R3 scripts are not edited. Every call adds `--dataset
<dataset> --val-nn-tau <tau> --seeds 15 --workers 3 --no-fidelity --out
results/phaseR/r3/<dataset>`:

```
--scenarios control --models rf xgboost                                          # reused
--scenarios a1 --models rf xgboost --jitters 0 --ratios 0.01 0.02 0.05 0.1       # stage a
--scenarios a1 --models rf xgboost --jitters 0 --ratios 0.5                      # reused (R3.1)
for c in 0.005 0.01 0.02 0.05:                                                   # 0.05 reused (R3.3)
  --scenarios a1 --models rf xgboost --jitters 0 --ratios 0.5 --defense sharecap --share-cap c
for d in none, sharecap 0.005/0.01/0.02/0.05, uniform --uniform-w 0.05:
  --scenarios s0 --models rf xgboost --ratios 0.2 --defense d
```

Per dataset that is 390 new jobs: stage a 120, stage-b A1 90, S0 180. Smoke test first, with
`SMOKE=1` (1 seed, 2 rounds) on NF-UNSW-NB15-v2 into a scratch root. Statistics are in
`experiments/phaseR_r3_4_stats.py`, and the results are appended to `docs/phaseR/r3-results.md`
as "R3.4".
