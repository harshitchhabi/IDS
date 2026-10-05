# Phase A session: retention (item C)

Read `docs/phaseA/common.md` first, then do item **C** from `docs/DECISIONS.md` §29 ("29.C
Retention: sliding window vs. accumulate").

**Branch:** `phase-a-retention`

## What you're testing

Whether A1's fixed-threshold FPR damage (the paper's largest, most robustly confirmed effect —
CICIDS2017, RF, jitter 0, both ratios) is specific to `accumulate` retention (honeypot influence
never ages out) or survives under `sliding_window` (only the last `window_rounds` rounds of
honeypot batches are kept). Both retention modes already exist in
`src/dloop/loop/config.py`'s `LoopConfig` — no new code needed, this item is purely runs +
statistics.

## Setup

```
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p results/phaseA/retention
```

Data: `--dataset cicids`, the original release only — same as item A. See
`docs/phaseA/common.md` §2.

Sanity check before the real run:

```
python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios control a1 --models rf --jitters 0 --ratios 0.2 \
  --retention sliding_window --window 5 \
  --seeds 1 --rounds 2 --workers 1 --out .smoke --no-fidelity
ls .smoke/jobs/
rm -rf .smoke
```

This exact command (at 1 seed, `--window 5` and separately `--window 10`, against synthetic data)
ran clean locally before this file was written. If it errors here against real CICIDS2017 data,
stop and report the error rather than debugging the pipeline yourself.

## The real runs

Three retention settings, all written fresh into `results/phaseA/retention/` — including
`accumulate`. `results/phase0/loop/cicids_recal/jobs/` in the main repo has `a1` at jitter 0 for
only 5 of the 15 seeds this family needs, and that directory is the already-published paper's
frozen evidence (every number in it traces to the paper as submitted) — **do not add seeds to it,
and do not read a mix of "5 seeds from there, 10 seeds computed here"** for the accumulate row.
Run accumulate fresh, into your own output directory, same as the other two settings. The modest
duplicated compute (this cell is cheap — RF, jitter 0, 2 ratios) is the right trade for not
touching frozen paper evidence.

```
nohup python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios control a1 --models rf --jitters 0 --ratios 0.2 0.5 \
  --seeds 15 --workers 3 --out results/phaseA/retention --no-fidelity \
  > results/phaseA/retention/run_accumulate.log 2>&1 &
```

Then, once that finishes:

```
nohup python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios control a1 --models rf --jitters 0 --ratios 0.2 0.5 \
  --retention sliding_window --window 5 \
  --seeds 15 --workers 3 --out results/phaseA/retention --no-fidelity \
  > results/phaseA/retention/run_w5.log 2>&1 &
```

```
nohup python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios control a1 --models rf --jitters 0 --ratios 0.2 0.5 \
  --retention sliding_window --window 10 \
  --seeds 15 --workers 3 --out results/phaseA/retention --no-fidelity \
  > results/phaseA/retention/run_w10.log 2>&1 &
```

## Compute the statistics

Six cells total: {accumulate, sliding_window w=5, sliding_window w=10} × {ratio 0.2,
ratio 0.5}, each a paired delta (A1 final-round fixed-threshold FPR minus the same-seed control,
same retention policy) against the matched control under that *same* retention policy — not
against the `accumulate` control. Holm correction within this one 6-cell family. Adapt
`experiments/phase0_stats_recompute.py`'s paired-t / permutation code (don't reimplement it).

## Write up

`docs/phaseA/retention-results.md`: one 6-row results table, then one paragraph stating
replicated / did not replicate / mixed against the exact §29.C bar (quoted, not paraphrased),
naming which specific window size / ratio combinations passed and which didn't if the result is
mixed.

Commit and push every hour or after each of the two runs above finishes. Do not touch
`docs/DECISIONS.md`, `paper/`, the demo/dashboard, or `scripts/`.
