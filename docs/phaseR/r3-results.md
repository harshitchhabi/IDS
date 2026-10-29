# R3 results: common-feature datasets (UQ NetFlow v2)

**Branch:** `harshit/wonderful-hawking-g2q1ju`

*In progress. Sections below are filled as each stage finishes.*

## Run environment

- Merged `origin/main` at 01f90c4 (normalizer float64 `log1p` fix, §31.8) before any counted run.
- `uv sync --frozen`: xgboost 3.4.1, scikit-learn 1.9.0, numpy 2.5.2.
- Output produced before the fix (NF-UNSW-NB15-v2 prep: grid sweep, degeneracy, 27 tau-sweep
  jobs) is archived unanalysed under `results/phaseR/r3_prefix/`. Nothing from it is used.
- `data/loop/cicids.npz` rebuilt with the fix: `pool_benign_x` = 344,221 rows (the published count).
- Smoke test (`SMOKE=1`, NF-UNSW-NB15-v2, both stages) rerun after the merge: both exit 0, 17
  stage-2 jobs, grid 0.0 invalid and 0.005-0.05 valid, as documented.

## Data

All three subsamples present in IDS-data: NF-UNSW-NB15-v2, NF-CSE-CIC-IDS2018-v2, NF-ToN-IoT-v2.

## Grid and tau per dataset

### NF-UNSW-NB15-v2

**Grid:** 0.005 (passes `assert_disjoint`; 0.0 is invalid, `prod_benign` empty). Unchanged.

**Tau: 0.2, by the fallback.** No tau in the set meets the bar (control fixed-threshold FPR,
rounds 11-20, 5 seeds, <= 0.015 for both RF and XGBoost). `phaseA_tau_floor.py` printed `nan`.
§31.3: "If no tau qualifies, tau = 0.2 and the write-up says so." The closest miss is tau 0.1
(RF 0.01512, XGBoost 0.01162).

`tau_sweep/control_floor_by_tau.csv`:

| tau | RF FPR | XGB FPR | val benign dropped |
|---|---:|---:|---:|
| 0 | 0.0578 | 0.0674 | 0.000 |
| 0.005 | 0.0348 | 0.0356 | 0.419 |
| 0.01 | 0.0285 | 0.0295 | 0.583 |
| 0.02 | 0.0243 | 0.0272 | 0.679 |
| 0.05 | 0.0192 | 0.0148 | 0.807 |
| 0.1 | 0.0151 | 0.0116 | 0.891 |
| 0.2 | 0.0578 | 0.0674 | 0.000 |

**Limitation, flagged before stage 2.** At tau 0.2 fewer than 100 twin-free benign validation
rows remain, so `BaseDetector._val_rows_without_twins` falls back to calibrating on every row
(`src/dloop/models/base.py`). Tau 0.2 is therefore numerically identical to tau 0 on this dataset
(table rows match exactly; 0 dropped). The pre-registered fallback, applied as written, runs
stage 2 with *no* twin filter and the highest control FPR in the sweep, not the strictest
filter. Reported here instead of substituting tau 0.1.

### NF-CSE-CIC-IDS2018-v2

**Grid:** 0.005 (passes `assert_disjoint`; here 0.0 is valid too, `near_dup_benign` 0, but
§31.3's rule and the committed `NETFLOW_GRID` keep 0.005). Unchanged.

**Tau: 0.** Every tau meets the bar; the rule takes the smallest. `phaseA_tau_floor.py` printed 0.0.

| tau | RF FPR | XGB FPR | val benign dropped |
|---|---:|---:|---:|
| 0 | 0.0066 | 0.0127 | 0.000 |
| 0.005 | 0.0057 | 0.0113 | 0.151 |
| 0.01 | 0.0050 | 0.0109 | 0.228 |
| 0.02 | 0.0047 | 0.0094 | 0.363 |
| 0.05 | 0.0047 | 0.0079 | 0.562 |
| 0.1 | 0.0027 | 0.0055 | 0.724 |
| 0.2 | 0.0019 | 0.0023 | 0.886 |
