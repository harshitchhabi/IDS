# Phase R session: R1 power

Read `docs/phaseR/common.md` first, then do item **R1** from `docs/DECISIONS.md` §31.1 (R1.a, R1.b,
R1.c). CICIDS2017 only.

## Setup

Data and cache per `common.md` §2. R1 needs only CICIDS2017:

```
python -m experiments.phase0_loop_data --source cicids
```

## Run

One script runs all three families in order (R1.a, then R1.b, then R1.c):

```
mkdir -p results/phaseR/r1
nohup bash experiments/run_phaseR_r1.sh > results/phaseR/r1/run.log 2>&1 &
```

What it runs (`experiments/run_phaseR_r1.sh` is the source of truth):

| family | output | jobs |
|---|---|---:|
| R1.a: control + A1, RF and XGBoost, 9 jitters x ratios 0.2/0.5, **`--eval-redraw`**, 15 seeds | `results/phaseR/r1/grid36/` | 570 |
| R1.b: control + A1, XGBoost, jitter 0, ratio 0.5, default eval, 30 seeds | `results/phaseR/r1/fixed/` | 60 |
| R1.c: control + A1, RF, jitters 0.01/0.03/0.10 x ratios 0.2/0.5, default eval, 15 seeds | `results/phaseR/r1/fixed/` | 105 |

R1.b and R1.c share `results/phaseR/r1/fixed/`. Job keys differ by model and jitter, and the
RF / XGBoost controls are separate jobs, so nothing collides. R1.a's jobs carry an `_evr` key
suffix. Commit and push after each family finishes (the log prints `>>>` before each).

## Checks before any statistic

1. **Reproduction (R1.b, R1.c).** Seeds 1-5 of R1.b's A1 cell and R1.c's six cells use the
   default eval subsample and must reproduce the published job CSVs in
   `results/phase0/loop/cicids_recal/jobs/` (same file name; compare `fpr`, `tpr`, `threshold`
   and the confusion counts per round and threshold mode). They were bit-identical for
   `a1_xgboost_s1_j0.0_r0.5_vt0.1.csv` when §31 was committed. A mismatch is a determinism bug:
   report it first, before any verdict (§31.1).
2. **Pairing (R1.a).** Every `_evr` job's per-round `n_seen_both` / `n_seed_only` /
   `n_honeypot_only` and benign row count (`tn + fp`) must equal its same-seed control's. Same
   eval draw, so the deltas are paired.

## Statistics

`experiments/phaseR_r1_stats.py` (yours to write; import the machinery from
`experiments/phase0_stats_recompute.py`):

- **R1.a.** 36 cells, outcome $\Delta$TPR recalibrated (final round, A1 minus same-seed control,
  both `_evr`), one Holm family of 36. Table: cell, $n$, mean, 95% CI, $t$, $p_t$,
  $p_{\rm perm}$, Holm survives (negative direction) at $n=15$, and the s26.1 $n=5$ status next
  to it. List the cells that newly clear and the cells that no longer clear. Also report the
  descriptive eval-draw sensitivity named in §31.1.
- **R1.b.** Round-10 fixed-threshold FPR per seed (30 rows, plus the full rounds-2-to-20 row per
  seed, like s25.6's table). Mode counts with the §31.1 cuts, and the Clopper-Pearson 95% CI on
  the high-mode share.
- **R1.c.** 6 cells, $\Delta$TPR recalibrated, one Holm family of 6.

## Write up

`docs/phaseR/r1-results.md`: branch name, the two checks above, then one section per family with
its table, then the verdict paragraphs against the three §31.1 bars (quoted), then the
`common.md` §6 table. Commit, push, stop.

## Smoke-tested

All three commands ran to completion at `--seeds 1 --rounds 2`
(`SMOKE=1 ROOT=.smoke/phaseR bash experiments/run_phaseR_r1.sh`) before §31 was committed.
