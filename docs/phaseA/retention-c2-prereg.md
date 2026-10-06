# Phase A item C2 — retention under a constant attacker budget (pre-registration)

**Written and committed before any C2 run, including the smoke test.** The commit timestamp of
this file is the pre-registration. `docs/DECISIONS.md` is not edited. Results go in a "C2"
section appended to `docs/phaseA/retention-results.md`. Nothing here may be changed after a C2
number has been seen. Any disagreement found later goes in the results section.

## Why

Item C (`docs/phaseA/retention-results.md`) ran §29.C under `budget_mode = fixed_ratio`. In that
mode the adversary's per-round batch grows under a sliding window so that the final-round honeypot
share is identical across retention settings by construction (7,500 of 37,500 rows at ratio 0.2;
30,000 of 60,000 at 0.5). Item C therefore could not test whether a window lets old poison age
out. C2 holds the adversary's **per-round volume** constant instead, so the windowed honeypot
share plateaus below the accumulated one.

## Question

Under a constant attacker budget, does sliding-window retention reduce A1's fixed-threshold FPR
damage compared with accumulate?

## Design

- CICIDS2017 (original release), `--val-nn-tau 0.1`, RF, A1 at jitter 0, 15 seeds (1-15),
  20 rounds, `--no-fidelity`.
- `--budget-mode fixed_batch`, batch sizes **375** and **1500** rows/round. These are item C's
  `accumulate` per-round sizes at ratio 0.2 and 0.5 (`0.2/0.8 × 30,000 / 20 = 375`;
  `0.5/0.5 × 30,000 / 20 = 1,500`), so under `accumulate` the final poison share matches item C
  (0.2 and 0.5). Under w=5 the final honeypot rows are 1,875 / 7,500 (share ≈ 0.059 / 0.2); under
  w=10 they are 3,750 / 15,000 (share ≈ 0.111 / 0.333).
- Retention: `accumulate`, `sliding_window` w=5, `sliding_window` w=10.
- Matched control: `control` run in the same invocation, under the same retention and budget
  setting. (Controls carry no honeypot data, so their FPR should not depend on either setting.
  Each invocation still gets its own, and every delta pairs with the control whose job tag
  matches.)

### How the CLI expresses this (checked in `experiments/phase0_loop.py` before writing)

- Under `--budget-mode fixed_batch` the runner ignores `--ratios` and builds each A1 job with
  ratio 0.0 (`for ratio in (args.ratios if args.budget_mode == "fixed_ratio" else (0.0,))`), so
  `--ratios` is omitted below.
- `--batch-size` takes one integer, so each (retention, batch size) pair is its own
  invocation: **6 invocations**.
- Job keys carry `LoopConfig.tag()` = `_{acc|w5|w10}_b{375|1500}_vt0.1`, so the six
  invocations do not collide in one `--out` directory, and none collides with item C's
  `fixed_ratio` jobs (tagged `_w5_fr` / `_w10_fr` / no tag).
- The job CSVs record `budget_mode` and `retention` but neither the window size nor the batch
  size. The stats read both from the job-file name's tag and assert that the tag agrees with the
  recorded `retention` and `budget_mode` columns.

### Exact commands

```
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p results/phaseA/retention-c2

# smoke test (1 seed, 2 rounds), output deleted afterwards
python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios control a1 --models rf --jitters 0 \
  --budget-mode fixed_batch --batch-size 375 --retention sliding_window --window 5 \
  --seeds 1 --rounds 2 --workers 1 --out .smoke --no-fidelity
rm -rf .smoke

# the six runs (B in {375, 1500})
python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios control a1 --models rf --jitters 0 \
  --budget-mode fixed_batch --batch-size B \
  --seeds 15 --workers 3 --out results/phaseA/retention-c2 --no-fidelity \
  > results/phaseA/retention-c2/run_acc_bB.log 2>&1

python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios control a1 --models rf --jitters 0 \
  --budget-mode fixed_batch --batch-size B --retention sliding_window --window 5 \
  --seeds 15 --workers 3 --out results/phaseA/retention-c2 --no-fidelity \
  > results/phaseA/retention-c2/run_w5_bB.log 2>&1

python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios control a1 --models rf --jitters 0 \
  --budget-mode fixed_batch --batch-size B --retention sliding_window --window 10 \
  --seeds 15 --workers 3 --out results/phaseA/retention-c2 --no-fidelity \
  > results/phaseA/retention-c2/run_w10_bB.log 2>&1
```

Each invocation runs 45 jobs: 15 control and 15 seeds × 1 A1 cell.

## Statistics

The functions `paired_deltas`, `paired_permutation_p` and `report_cell` are imported from
`experiments/phase0_stats_recompute.py` unchanged. That means: paired $t$ (two-sided); a two-sided
sign-flip permutation test, Monte Carlo with 10,000 resamples since $n = 15 > 12$; 95% $t$ CI.
Everything is measured at the final round (round 20) with the **fixed** threshold. **Paired $t$
is primary** (project convention, s27); the permutation $p$ is reported alongside, with Holm
applied to it separately for transparency. Holm-Bonferroni step-down, $\alpha = 0.05$, within
each family only.

### Family C2.1 — damage (6 cells, descriptive of where damage exists)

For each retention × batch size: per seed, ΔFPR = A1 FPR minus the same seed's control FPR,
using the control from the matching invocation. Holm within the 6. Each cell is reported as
clears / does not clear Holm, with its sign. This family has no overall verdict.

### Family C2.2 — the real question (4 cells)

For w ∈ {5, 10} × B ∈ {375, 1500}: per seed, contrast = (ΔFPR under w, batch B) − (ΔFPR under
accumulate, batch B), with the seeds aligned. Holm within the 4.

**Bar, per cell:** "windowing reduces damage" for that (w, B) iff its C2.2 contrast has a
**negative** mean **and** its two-sided paired-$t$ $p$ clears its Holm threshold within C2.2.
Otherwise the result for that cell is "no reduction shown". If the contrast clears Holm with a
positive mean, the result is "windowing increases damage". Reported per cell, not collapsed to
one verdict.

## Descriptive checks (not tested; stated now so they can't be chosen later)

- `accumulate` at B=375 and B=1500 should reproduce item C's `accumulate` ratio 0.2 / 0.5 job
  outputs. The per-round budgets are identical (375 and 1,500 in every round), and so are the
  seeds and code. Any difference gets reported as a pipeline inconsistency, not explained away.
- Per-round mean A1 FPR and `n_honeypot` trajectories for all 6 settings.
- Controls: identical per-round FPR across all 6 invocations.
