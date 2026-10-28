# Phase R session: R3 common-feature datasets (UQ NetFlow v2)

Read `docs/phaseR/common.md` first, then do item **R3** from `docs/DECISIONS.md` §31.3.

## Before anything: is the data there?

R3's data is a manual download (§31.4). After cloning `IDS-data` (`common.md` §2), check that
`data/netflow-v2/` holds the three CSVs the loader expects, under exactly these names:

```
data/netflow-v2/NF-UNSW-NB15-v2.csv
data/netflow-v2/NF-CSE-CIC-IDS2018-v2.csv
data/netflow-v2/NF-ToN-IoT-v2.csv
```

Each comes with a `<stem>.sampling.json` recording the stratified subsample (§31.3). If none of
the three is there, stop: write one sentence in `docs/phaseR/r3-results.md` saying so, push, and
end. If only some are, run R3 on those and name the missing ones in one sentence. Do not
substitute another dataset.

The column mapping is already committed (`dloop.features.schema.NETFLOW_V2_COLUMN_MAP`, §31.3).
If the loader stops on a missing column, report the header it printed. Do not edit the mapping.

## Run, per dataset

`<dataset>` is `nf-unsw-nb15-v2`, `nf-cse-cic-ids2018-v2` or `nf-ton-iot-v2`. Two stages, one
dataset at a time.

**Stage 1, prep** (loop cache, near-duplicate grid sweep, R3.0 degeneracy, tau sweep and the
§31.3 tau rule):

```
mkdir -p results/phaseR/r3/<dataset>
nohup bash experiments/run_phaseR_r3.sh <dataset> prep > results/phaseR/r3/<dataset>/run_prep.log 2>&1 &
```

When it finishes:

1. **Grid.** Read `results/phaseR/r3/<dataset>/grid_sweep.csv`. If grid 0.005 passes
   `assert_disjoint`, nothing changes. If it fails, set that dataset's entry in
   `experiments/_common.py`'s `NETFLOW_GRID` to the gentlest grid that passes (§31.3's rule),
   commit that one-line change with the sweep, and **rerun stage 1** so the cache, degeneracy
   table and tau sweep use the chosen grid.
2. **Tau.** The last lines of the log print the tau the rule chose
   (`experiments/phaseA_tau_floor.py`, unmodified). That number is `<tau>` below. Record it, with
   `tau_sweep/control_floor_by_tau.csv`, in the write-up before stage 2 starts.

**Stage 2, main** (R3.1 damage grid, R3.2 mechanism arms, R3.3 ShareCap c = 0.05, all 15 seeds):

```
nohup bash experiments/run_phaseR_r3.sh <dataset> main <tau> > results/phaseR/r3/<dataset>/run_main.log 2>&1 &
```

| stage | jobs per dataset |
|---|---:|
| prep: tau sweep (7 taus x control x RF/XGBoost x 5 seeds) | 70 |
| main: R3.1 (control + A1, 2 jitters x 2 ratios, RF/XGBoost) | 270 |
| main: R3.2 (a1truth, s0j at jitter 0.7; junk; RF, ratio 0.2) | 45 |
| main: R3.3 (A1 under ShareCap 0.05, ratios 0.2/0.5, RF/XGBoost) | 60 |

Commit and push after each stage of each dataset.

## Statistics

`experiments/phaseR_r3_stats.py` (yours to write; adapt `experiments/phaseA_datasets_stats.py`,
which does R3.1/R3.2's structure for Phase A's datasets). Per dataset: the R3.0 degeneracy table
(from `nn_degeneracy_by_grid.csv`); R3.1's 8-cell Holm family per model; R3.2's 4-arm Bonferroni
family plus the secondary a1-minus-a1truth contrast; R3.3's $R$ at ratio 0.5 (and 0.2,
descriptive), with $R$ computed against R3.1's undefended A1 at the same seed.

## Write up

`docs/phaseR/r3-results.md`: branch name, the data situation (which datasets, rows before and
after subsampling from each `sampling.json`), the grid and tau per dataset, then per dataset R3.0
to R3.3 with verdicts against the §31.3 bars (quoted), then the cross-dataset summary table §31.3
asks for, then the `common.md` §6 table. Commit, push, stop.

## Smoke-tested: the command chain, not the real data

None of these commands could be smoke-tested on real data before §31 was committed: the NetFlow
v2 files did not exist yet (§31.4). What was tested:

- Both stages (`prep`, then `main`) of `experiments/run_phaseR_r3.sh nf-ton-iot-v2` at 1 seed / 2
  rounds (`SMOKE=1`), against a **synthetic** CSV carrying the NetFlow v2 header, placed at
  `data/netflow-v2/NF-ToN-IoT-v2.csv` and deleted afterwards. That covers the loader, the cache
  build, grid sweep, degeneracy, the 7-tau control sweep, and every stage-2 arm. The tau floor
  needs rounds 11-20, so it is skipped under `SMOKE=1`; it is Phase A's script, unmodified.
- `tests/test_phaseR.py`: the loader (column mapping, unit conversion, label consistency, a
  missing column refused), partitioning and a loop arm on the 29-feature set, and the
  subsampler.

**So the first real stage-1 run is also the real-data smoke test.** If anything in it errors,
stop and report it rather than patching the pre-registered script.
