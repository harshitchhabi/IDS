# Phase A session: models (item A)

Read `docs/phaseA/common.md` first, then do item **A** from `docs/DECISIONS.md` §29 ("29.A
Models: logistic regression and a small MLP behind the existing interface").

**Branch:** `phase-a-models`

## What you're testing

Whether A1's damage and the label-conflict mechanism reproduce on two models with a different
inductive bias than RF/XGBoost: `LogRegModel` (`src/dloop/models/logreg.py`) and `MLPModel`
(`src/dloop/models/mlp.py`). Both already exist, are wired into `MODELS` in
`src/dloop/models/__init__.py`, and are covered by `tests/test_models.py`'s parametrized suite —
you are not implementing new models, you are running the existing ones at scale.

## Setup

```
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p results/phaseA/models
```

Data: item A only needs CICIDS2017 (`--dataset cicids`) — the original release, not the
reprocessed one. `docs/phaseA/common.md` §2 covers getting it; you need `data/cicids2017/` only
(not `cicids2017-fixed/` or `unsw-nb15/`).

Sanity check before the real run — this should finish in well under a minute and produce 4 files
under `.smoke/jobs/`:

```
python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios control a1 --models logreg mlp --jitters 0.7 --ratios 0.2 \
  --seeds 1 --rounds 2 --workers 1 --out .smoke --no-fidelity
ls .smoke/jobs/
rm -rf .smoke
```

If that errors, stop and report the error rather than debugging the pipeline itself — this exact
command (at 1 seed locally, before this file was written) ran clean, so an error here means
something about the cloud environment differs (package version, CICIDS2017 files not fully
extracted, etc.), which is worth flagging rather than working around silently.

## The real runs (background, nohup, per §29.A / `docs/phaseA/common.md` §4)

```
nohup python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios control a1 --models logreg mlp --jitters 0 0.7 --ratios 0.2 0.5 \
  --seeds 15 --workers 3 --out results/phaseA/models --no-fidelity \
  > results/phaseA/models/run_damage.log 2>&1 &
```

Wait for that to finish (check `run_damage.log` / job-file count roughly every 15 minutes, per
common.md §4), then:

```
nohup python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios a1truth s0j --models logreg mlp --jitters 0.7 --ratios 0.2 \
  --seeds 15 --workers 3 --out results/phaseA/models --no-fidelity \
  > results/phaseA/models/run_mech1.log 2>&1 &
```

```
nohup python -m experiments.phase0_loop --dataset cicids --val-nn-tau 0.1 \
  --scenarios junk --models logreg mlp --jitters 0.0 --ratios 0.2 \
  --seeds 15 --workers 3 --out results/phaseA/models --no-fidelity \
  > results/phaseA/models/run_mech2.log 2>&1 &
```

(`a1` at ratio 0.2, jitter 0.7 — needed for family A.2 — already exists from the first run; it is
not rerun here.)

## Compute the statistics

Reuse `experiments/phase0_stats_recompute.py`'s paired-t / permutation machinery rather than
reimplementing it — read that script first; it already knows how to pull same-seed deltas from
job CSVs under a `jobs/` directory and run both tests with Holm/Bonferroni correction. Point it at
`results/phaseA/models/jobs/` and adapt its family definitions to §29.A's two families (8-cell
damage grid per model, Holm; 4-arm mechanism isolation per model, Bonferroni) instead of this
paper's own families.

## Write up

`docs/phaseA/models-results.md`, structured per `docs/phaseA/common.md` §6: one results table
(16 damage-grid cells + 8 mechanism-isolation cells = 24 rows), then one paragraph per model
stating replicated / did not replicate / mixed against the §29.A bar, quoted exactly.

Commit and push every hour or after each of the three runs above finishes. Do not touch
`docs/DECISIONS.md`, `paper/`, the demo/dashboard, or `scripts/`.
