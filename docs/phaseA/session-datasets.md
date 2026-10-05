# Phase A session: datasets (item B)

Read `docs/phaseA/common.md` first, then do item **B** from `docs/DECISIONS.md` §29 ("29.B
Datasets: reprocessed CICIDS2017 and UNSW-NB15").

**Branch:** `phase-a-datasets`

## What's different about this item

Unlike items A and C, the code this item needs does not exist yet — **building it is the first
half of the job**, not prep that was done for you. `src/dloop/sim/cicids.py` is your template:
read the raw files, map columns onto `dloop.features.schema.CANONICAL_FEATURES`, tag whatever
the dataset's analogue of "capture day" is, return per-partition frames the rest of the pipeline
already knows how to consume. `src/dloop/sim/dataset.py`'s `Source` literal and `load_partitions`
dispatch need a new branch per dataset you actually run (mirroring the existing `"cicids"`
branch).

Do this **before** running anything, and document the column mapping you chose in
`docs/phaseA/datasets-results.md` before computing a single number from it — §29.B is explicit
that a mapping decision made after seeing results is exactly the kind of thing this project
pre-registers against.

## Which datasets, and whether they're there at all

Check `https://github.com/harshitchhabi/IDS-data`'s own README first. It was last known to
contain:
- `cicids2017/` — the original CICIDS2017 release (you don't need this for item B; item A uses it)
- `cicids2017-fixed/` — Engelen et al.'s reprocessed CICIDS2017 (91 columns per row; the README
  lists them and notes the column-name differences from the original release)
- `unsw-nb15/` — **may not exist.** The official UNSW-NB15 distribution needs a manual browser
  download (SharePoint, not scriptable) that may not have happened yet. If `unsw-nb15/` is absent
  or empty, run only the `cicids2017-fixed` half of this item and say so plainly in the results
  write-up — do not substitute a different dataset or skip silently.

Get the data per `docs/phaseA/common.md` §2.

## Build the loader (per dataset you're actually running)

1. New module, e.g. `src/dloop/sim/cicids_fixed.py` (and/or `src/dloop/sim/unsw_nb15.py`):
   read the raw CSV(s), rename columns onto `CANONICAL_FEATURES`
   (`src/dloop/features/schema.py`) as closely as the dataset's own fields allow, tag a
   day/session column for the temporal partition split. `cicids_fixed`'s columns are close to the
   original CICIDS2017's (see the IDS-data README for the exact list and naming differences);
   UNSW-NB15's are not (`unsw-nb15/NUSW-NB15_features.csv`, if you downloaded it, is the column
   dictionary — use it rather than guessing from header names alone). Where a canonical feature
   has no real analogue in a dataset, leave it out of that dataset's run rather than fabricating
   a zero column, and say which features were dropped in the write-up.
2. Add the matching `Source` branch in `src/dloop/sim/dataset.py`'s `load_partitions` /
   `load_raw` dispatch, and a `--dataset` choice in `experiments/phase0_loop.py`'s argument
   parser (currently `choices=["cicids", "synthetic"]` — extend it, don't replace it).
3. Smoke test with 1 seed / 2 rounds before anything larger, same pattern as the other two items:
   ```
   python -m experiments.phase0_loop --dataset <your-new-choice> --scenarios control a1 \
     --models rf --jitters 0.7 --ratios 0.2 --seeds 1 --rounds 2 --workers 1 \
     --out .smoke --no-fidelity
   ```
   Delete `.smoke/` once it passes.

## Family B.0 — degeneracy measurement, per dataset (run this before B.1/B.2)

Compute the median per-feature-RMS nearest-neighbour distance (guard-(c) metric, normalized
space) from `trusted_eval` to the honeypot-pool-equivalent partition, every family with ≥500 eval
rows, benign included — the same measurement `experiments/phase0_degeneracy*.py` already performs
for CICIDS2017 (read that script; reuse its distance code rather than reimplementing it). Also
derive `val-nn-tau` for this dataset the way s19 derived 0.1 for CICIDS2017: the smallest tau that
brings the undefended control's fixed-threshold FPR close to the 0.01 target. Record both in
`docs/phaseA/datasets-results.md` — the tau you derive here is what families B.1/B.2 use; it is
very unlikely to be 0.1 again, since that number is specific to CICIDS2017's own near-degeneracy.

## Families B.1 / B.2 — the actual runs, per dataset

```
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
mkdir -p results/phaseA/datasets/<dataset>

nohup python -m experiments.phase0_loop --dataset <dataset> --val-nn-tau <measured> \
  --scenarios control a1 --models rf xgboost --jitters 0 0.7 --ratios 0.2 0.5 \
  --seeds 15 --workers 3 --out results/phaseA/datasets/<dataset> --no-fidelity \
  > results/phaseA/datasets/<dataset>/run_damage.log 2>&1 &
```

Then, once that finishes:

```
nohup python -m experiments.phase0_loop --dataset <dataset> --val-nn-tau <measured> \
  --scenarios a1truth s0j --models rf --jitters 0.7 --ratios 0.2 \
  --seeds 15 --workers 3 --out results/phaseA/datasets/<dataset> --no-fidelity \
  > results/phaseA/datasets/<dataset>/run_mech1.log 2>&1 &

nohup python -m experiments.phase0_loop --dataset <dataset> --val-nn-tau <measured> \
  --scenarios junk --models rf --jitters 0.0 --ratios 0.2 \
  --seeds 15 --workers 3 --out results/phaseA/datasets/<dataset> --no-fidelity \
  > results/phaseA/datasets/<dataset>/run_mech2.log 2>&1 &
```

Repeat for the second dataset if both are available. These are two independent sets of runs
(reprocessed-CICIDS2017 and UNSW-NB15) — do not pool their job directories.

## Compute the statistics

Same approach as the other two items: adapt `experiments/phase0_stats_recompute.py`'s paired-t /
permutation machinery (don't reimplement it) to §29.B's families — 8-cell damage grid per
(dataset, model), Holm; 4-arm mechanism isolation per dataset, Bonferroni.

## Write up

`docs/phaseA/datasets-results.md`: the column-mapping decision first (per dataset), then the B.0
degeneracy table, then one results table per dataset for B.1+B.2 (16 + 4 = 20 rows per dataset),
then one paragraph per (dataset, model) stating replicated / did not replicate / mixed against the
§29.B bar, quoted exactly. If UNSW-NB15 was not available, its section says so in one sentence —
do not pad it.

Commit and push every hour or after each sub-step. Do not touch `docs/DECISIONS.md`, `paper/`,
the demo/dashboard, or `scripts/` — the new loader code belongs under `src/dloop/sim/` and
`src/dloop/features/`, same as every other dataset this project already supports.
