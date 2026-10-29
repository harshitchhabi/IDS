# R3 results: common-feature datasets (UQ NetFlow v2)

**Branch:** `harshit/wonderful-hawking-g2q1ju`

## Run environment

- Merged `origin/main` at 01f90c4 (normalizer float64 `log1p` fix, §31.8) before any counted run
  (fast-forward).
- `uv sync --frozen`: **xgboost 3.4.1, scikit-learn 1.9.0**, numpy 2.5.2. 4 vCPU, `WORKERS=3`.
- Output produced before the fix (NF-UNSW-NB15-v2 prep: grid sweep, degeneracy, 27 tau-sweep
  jobs, stopped mid-sweep) is archived unanalysed under `results/phaseR/r3_prefix/`. Nothing from
  it is used below.
- `data/loop/cicids.npz` rebuilt with the fix: `pool_benign_x` = 344,221 rows (the published
  count). The NetFlow v2 caches are rebuilt by each dataset's prep stage.
- Smoke test (`SMOKE=1`, NF-UNSW-NB15-v2, both stages) rerun after the merge: both exit 0, 17
  stage-2 jobs, grid 0.0 invalid and 0.005-0.05 valid, as documented. `tests/test_phaseR.py`
  and `tests/test_normalize.py` pass.
- Statistics: `experiments/phaseR_r3_stats.py` (imports `phaseA_datasets_stats`'s cell
  selection and `phase0_stats_recompute`'s paired-$t$ / permutation tests). Per dataset it writes
  `results/phaseR/r3/<dataset>/{stats.csv, r3_0_degeneracy.csv, verdicts.json}`. "Clears Holm"
  means rejected by both tests in the damage direction, Phase A's reading of the same bar.

## Data

All three subsamples were present in IDS-data; none missing.

| dataset | rows before subsample | rows after (`sampling.json`) | after exact-dup cleaning | near-dup removed (grid 0.005) | seed_train / prod_benign / honeypot_pool / trusted_eval |
|---|---:|---:|---:|---:|---|
| NF-UNSW-NB15-v2 | 2,390,275 | 1,095,053 | 73,284 | 9,902 | 21,967 / 6,083 / 21,717 / 12,522 |
| NF-CSE-CIC-IDS2018-v2 | 18,893,708 | 2,037,335 | 429,450 | 146,203 | 101,299 / 23,731 / 101,186 / 56,555 |
| NF-ToN-IoT-v2 | 16,940,496 | 2,227,957 | 246,414 | 71,671 | 65,057 / 8,831 / 64,496 / 34,285 |

Subsample caps as pre-registered (200,000 per attack family, 1,000,000 benign; no benign-cap
lowering recorded in any `sampling.json`). Exact duplicates on the 29 mapped features are most
rows, as expected (§31.7): 93% of NF-UNSW-NB15-v2's subsample, 79% of NF-CSE-CIC-IDS2018-v2's,
89% of NF-ToN-IoT-v2's. `label_and_attack_disagree` = 0 on all three. Partitions logged
`leak_warning: true` on all three, as on NF-UNSW-NB15-v2's smoke test.

**Job counts.** Each dataset ran 70 prep jobs and 255 stage-2 jobs: R3.1 150, R3.2 45 (30 + 15),
R3.3 60. The session file's table lists 270 for R3.1. The pre-registered R3.1 command launches 2
models x (control + 4 A1 cells) x 15 seeds = 150. Each job records both threshold modes, so the
table's 270 does not match any count I can reconstruct. Every job the unmodified commands
launched finished, with no error in any log.

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

### NF-ToN-IoT-v2

**Grid:** 0.005 (passes `assert_disjoint`; 0.0 is valid here too, no near-duplicates, but the
committed `NETFLOW_GRID` and §31.3's rule keep 0.005). Unchanged.

**Tau: 0.** Every tau meets the bar; the rule takes the smallest. `phaseA_tau_floor.py` printed 0.0.

| tau | RF FPR | XGB FPR | val benign dropped |
|---|---:|---:|---:|
| 0 | 0.0044 | 0.0082 | 0.000 |
| 0.005 | 0.0037 | 0.0073 | 0.171 |
| 0.01 | 0.0036 | 0.0087 | 0.263 |
| 0.02 | 0.0034 | 0.0055 | 0.388 |
| 0.05 | 0.0025 | 0.0041 | 0.572 |
| 0.1 | 0.0022 | 0.0023 | 0.744 |
| 0.2 | 0.0006 | 0.0006 | 0.883 |

## Results per dataset

The §31.3 bars, quoted:

- R3.1: "copy-fidelity damage holds" iff both jitter-0 fixed-$\Delta$FPR cells clear Holm
  (positive); "does not hold" iff neither does; "mixed" iff one does.
- R3.2 primary (s28's): "holds" iff a1 clears $\alpha/4$ by both tests and every null arm's 95% CI
  includes 0; "does not hold" iff a1 fails $\alpha/4$; "mixed" otherwise.
- R3.2 secondary: "The label conflict does damage beyond the rows themselves" iff that contrast
  [a1 minus a1truth at the same seed] is negative with paired-$t$ $p<0.05$.
- R3.3: "holds" iff $R\ge0.90$; "does not hold" otherwise; "not evaluable" iff R3.1's
  ratio-0.5 jitter-0 $\Delta$FPR does not clear Holm.

Every cell's numbers are in the closing table.

### NF-UNSW-NB15-v2 (grid 0.005, tau 0.2 by fallback, effectively tau 0)

**R3.0 degeneracy.**

| class | family | eval rows @0.005 | 0.005 | 0.01 | 0.02 | 0.05 | tier @0.005 |
|---|---|---:|---:|---:|---:|---:|---|
| attack | ALL_ATTACK | 6262 | 0.0049 | 0.0076 | 0.0121 | 0.0208 | degenerate |
| attack | DoS | 618 | 0.0049 | 0.0056 | — | — | degenerate |
| attack | Exploits | 3856 | 0.0054 | 0.0080 | 0.0118 | 0.0189 | degenerate |
| attack | Fuzzers | 1122 | 0.0030 | 0.0060 | 0.0142 | 0.0353 | degenerate |
| benign | BENIGN | 6260 | 0.0180 | 0.0239 | 0.0329 | 0.0456 | degenerate |

**R3.1: holds, for both RF and XGBoost.** Jitter 0, fixed $\Delta$FPR: RF +0.173 (r=0.2), +0.240
(r=0.5); XGBoost +0.183, +0.240. All four clear Holm by both tests. At jitter 0.7 the damage
mostly goes away: RF $\Delta$FPR +0.016 (r=0.2, clears) and +0.018 (r=0.5, does not clear); XGBoost
$\Delta$FPR is slightly negative and does not clear. Jitter-0 recalibrated $\Delta$TPR is −0.04 to
−0.05 and clears Holm.

**R3.2 primary: does not hold.** a1 is −0.012 (p_t 0.18), which fails $\alpha/4$. Null arms:
a1truth +0.021 (CI includes 0), junk −0.001 (includes 0), s0j −0.019 (CI [−0.037, −0.00004],
excludes 0 by a hair). **Secondary: met.** a1 − a1truth = −0.033, p_t 0.0019.

**R3.3: does not hold, for both models.** R at ratio 0.5: RF 0.380 [bootstrap 0.310, 0.451];
XGBoost 0.524 [0.443, 0.608]. Evaluable: R3.1's bar cells clear. Ratio 0.2 (descriptive): RF
0.212, XGBoost 0.300.

### NF-CSE-CIC-IDS2018-v2 (grid 0.005, tau 0)

**R3.0 degeneracy.**

| class | family | eval rows @0.005 | 0.005 | 0.01 | 0.02 | 0.05 | tier @0.005 |
|---|---|---:|---:|---:|---:|---:|---|
| attack | ALL_ATTACK | 32782 | 0.0040 | 0.0058 | 0.0077 | 0.0157 | degenerate |
| attack | DDOS attack-HOIC | 2783 | 0.0037 | 0.0053 | 0.0074 | 0.0134 | degenerate |
| attack | DDoS attacks-LOIC-HTTP | 1473 | 0.0047 | 0.0059 | 0.0070 | 0.0111 | degenerate |
| attack | DoS attacks-GoldenEye | 4899 | 0.0083 | 0.0094 | 0.0116 | 0.0201 | degenerate |
| attack | DoS attacks-Hulk | 18162 | 0.0033 | 0.0048 | 0.0065 | 0.0115 | degenerate |
| attack | Infilteration | 2490 | 0.0568 | 0.0596 | 0.0625 | 0.0708 | degenerate |
| attack | SSH-Bruteforce | 2187 | 0.0013 | 0.0020 | — | — | degenerate |
| benign | BENIGN | 23773 | 0.0310 | 0.0347 | 0.0428 | 0.0550 | degenerate |

**R3.1: holds, for both RF and XGBoost.** Jitter 0, fixed $\Delta$FPR: RF +0.518 (r=0.2), +0.969
(r=0.5); XGBoost +0.909, +0.986. At ratio 0.5 the detector flags nearly every trusted benign
row. All 16 cells clear Holm, including jitter 0.7, where the effects are small (|Δ| < 0.008).

**R3.2 primary: mixed.** a1 clears $\alpha/4$ (−0.0019, p_t 3e-5), but no null arm's CI includes 0:
a1truth +0.0011, s0j −0.0022, junk −0.0016, each with p_t < 0.006. Condition met: a1 clears.
Condition failed: the null arms' CIs all exclude 0. **Secondary: met.** a1 − a1truth = −0.0030,
p_t 6e-8. These are tiny effects measured with very tight CIs on a large eval set.

**R3.3: holds, for both models.** R at ratio 0.5: RF 0.969 [0.964, 0.974]; XGBoost 0.960 [0.956,
0.963]. Ratio 0.2 (descriptive): RF 0.961, XGBoost 0.959.

### NF-ToN-IoT-v2 (grid 0.005, tau 0)

**R3.0 degeneracy.**

| class | family | eval rows @0.005 | 0.005 | 0.01 | 0.02 | 0.05 | tier @0.005 |
|---|---|---:|---:|---:|---:|---:|---|
| attack | ALL_ATTACK | 25310 | 0.0109 | 0.0153 | 0.0192 | 0.0309 | degenerate |
| attack | ddos | 6084 | 0.0220 | 0.0251 | 0.0302 | 0.0429 | degenerate |
| attack | injection | 7456 | 0.0132 | 0.0183 | 0.0236 | 0.0355 | degenerate |
| attack | password | 6569 | 0.0058 | 0.0087 | 0.0096 | 0.0159 | degenerate |
| attack | xss | 4227 | 0.0072 | 0.0114 | 0.0191 | 0.0300 | degenerate |
| benign | BENIGN | 8975 | 0.2707 | 0.2921 | 0.3348 | 0.4202 | degenerate |

**R3.1: holds, for both RF and XGBoost.** Jitter 0, fixed $\Delta$FPR: RF +0.242 (r=0.2), +0.270
(r=0.5); XGBoost +0.248, +0.275. All 16 cells clear Holm. Damage stays large at jitter 0.7
($\Delta$FPR +0.14 to +0.16). The recalibrated $\Delta$TPR collapse is the largest of the three
datasets: −0.57 to −0.65 for RF, −0.26 to −0.63 for XGBoost.

**R3.2 primary: mixed.** a1 clears $\alpha/4$ (−0.597, p_t 3e-13). No null arm's CI includes 0:
s0j −0.608 and junk −0.487, both as damaging as a1, and a1truth +0.073. Condition met: a1
clears. Condition failed: the null arms' CIs all exclude 0. **Secondary: met.** a1 − a1truth =
−0.670, p_t 4e-14. Here s0j (genuine attacks, correctly labelled) and junk do as much TPR damage
as a1. Read under §30's problem 2, that is consistent with a non-saturated detector being moved
by any honeypot rows at ratio 0.2, not specifically by the label conflict. The secondary contrast
separates a1 from a1truth, but not from s0j.

**R3.3: does not hold, for both models.** R at ratio 0.5: RF 0.226 [0.215, 0.237]; XGBoost
0.299 [0.287, 0.309]. Ratio 0.2 (descriptive): RF 0.199, XGBoost 0.214.

## Cross-dataset summary

| dataset | grid | tau | R3.0 (median NN RMS @0.005, all-attack / benign) | R3.1 RF | R3.1 XGB | R3.2 primary | R3.2 secondary | R3.3 RF (R@0.5) | R3.3 XGB (R@0.5) |
|---|---|---|---|---|---|---|---|---|---|
| NF-UNSW-NB15-v2 | 0.005 | 0.2 (fallback; = no filter) | 0.0049 / 0.0180 | holds | holds | does not hold | met | does not hold (0.380) | does not hold (0.524) |
| NF-CSE-CIC-IDS2018-v2 | 0.005 | 0 | 0.0040 / 0.0310 | holds | holds | mixed | met | holds (0.969) | holds (0.960) |
| NF-ToN-IoT-v2 | 0.005 | 0 | 0.0109 / 0.2707 | holds | holds | mixed | met | does not hold (0.226) | does not hold (0.299) |

On the shared 29-feature set, copy-fidelity FPR damage (R3.1) holds on every dataset and model.
The label-conflict secondary contrast is met on all three. The s28 primary bar holds on none,
because either a1 fails or the null arms move too. ShareCap c = 0.05 recovers ≥ 0.90 of A1's FPR
damage only on NF-CSE-CIC-IDS2018-v2. On NF-UNSW-NB15-v2 and NF-ToN-IoT-v2 it recovers 0.23-0.52.
Since the features are shared, §31.3 reads these as dataset differences.

## Limitations and disagreements

- **Tau fallback on NF-UNSW-NB15-v2.** Recorded before stage 2 (above): the pre-registered
  fallback tau = 0.2 is numerically the same as no twin filter on this dataset. That is because of
  the < 100-row fallback in `BaseDetector._val_rows_without_twins`. Its control FPR (0.058 RF,
  0.067 XGB) is the highest in the sweep. Stage 2 ran as pre-registered. The rule's intent (the
  strictest filter when nothing qualifies) is not what it does here.
- **R3.0 tier.** `phase0_degeneracy.py` labels every family on every dataset "degenerate" at grid
  0.005, including NF-ToN-IoT-v2 benign, whose median distance is 0.27. Reported as the script
  emits it. The medians are the informative column.
- **ShareCap at c = 0.05 is below the bar on two of three datasets.** This is not tuned. Per §25.5
  the cap depends on where damage starts for a given model and dataset, and R3 pre-registered
  only c = 0.05.
- **Session-file job count** (270 for R3.1) does not match the pre-registered command (150). See
  Data.
- **Stats bug found and fixed before any verdict was read.** The first R3.3 run of
  `phaseR_r3_stats.py` matched zero ShareCap rows: the job CSVs record `defense` as
  `sharecap_c0.05`, not `sharecap`. The filter now uses that tag and refuses fewer than 15 paired
  seeds.

## All cells (`common.md` §6)

R3.1 Holm is within each (dataset, model) family of 8, reported per test. R3.2 uses Bonferroni
α/4 = 0.0125 (both tests). R3.3's row is defended minus undefended $\Delta$FPR at the same seed,
with R and its seed-bootstrap 95% CI.

| cell | n | effect | 95% CI | $t$ | $p_t$ | $p_{\rm perm}$ | Holm | vs. §31 bar |
|---|---|---|---|---|---|---|---|---|
| nf-unsw-nb15-v2 R3.1 rf r=0.2 j=0.0 fixed dFPR | 15 | 0.1733 | [0.1574, 0.1892] | 23.39 | 1.28e-12 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-unsw-nb15-v2 R3.1 rf r=0.2 j=0.0 recalibrated dTPR | 15 | -0.05137 | [-0.06864, -0.03409] | -6.38 | 1.72e-05 | 0.0001 | t:rej / perm:rej | reported |
| nf-unsw-nb15-v2 R3.1 rf r=0.2 j=0.7 fixed dFPR | 15 | 0.01551 | [0.007548, 0.02346] | 4.18 | 0.000927 | 0.0016 | t:rej / perm:rej | reported |
| nf-unsw-nb15-v2 R3.1 rf r=0.2 j=0.7 recalibrated dTPR | 15 | -0.01204 | [-0.03052, 0.006436] | -1.40 | 0.184 | 0.1855 | t:no / perm:no | reported |
| nf-unsw-nb15-v2 R3.1 rf r=0.5 j=0.0 fixed dFPR | 15 | 0.2399 | [0.2274, 0.2524] | 41.17 | 5.21e-16 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-unsw-nb15-v2 R3.1 rf r=0.5 j=0.0 recalibrated dTPR | 15 | -0.0526 | [-0.07159, -0.03362] | -5.94 | 3.59e-05 | 0.0001 | t:rej / perm:rej | reported |
| nf-unsw-nb15-v2 R3.1 rf r=0.5 j=0.7 fixed dFPR | 15 | 0.01793 | [0.0001704, 0.0357] | 2.17 | 0.0481 | 0.0198 | t:no / perm:no | reported |
| nf-unsw-nb15-v2 R3.1 rf r=0.5 j=0.7 recalibrated dTPR | 15 | -0.01104 | [-0.02816, 0.006077] | -1.38 | 0.188 | 0.1973 | t:no / perm:no | reported |
| nf-unsw-nb15-v2 R3.1 xgboost r=0.2 j=0.0 fixed dFPR | 15 | 0.1828 | [0.1734, 0.1923] | 41.38 | 4.85e-16 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-unsw-nb15-v2 R3.1 xgboost r=0.2 j=0.0 recalibrated dTPR | 15 | -0.04309 | [-0.06643, -0.01974] | -3.96 | 0.00143 | <0.0001 | t:rej / perm:rej | reported |
| nf-unsw-nb15-v2 R3.1 xgboost r=0.2 j=0.7 fixed dFPR | 15 | -0.01126 | [-0.02412, 0.001606] | -1.88 | 0.0815 | 0.0805 | t:no / perm:no | reported |
| nf-unsw-nb15-v2 R3.1 xgboost r=0.2 j=0.7 recalibrated dTPR | 15 | -0.01322 | [-0.02489, -0.001554] | -2.43 | 0.0291 | 0.0075 | t:no / perm:rej | reported |
| nf-unsw-nb15-v2 R3.1 xgboost r=0.5 j=0.0 fixed dFPR | 15 | 0.2398 | [0.229, 0.2505] | 47.77 | 6.59e-17 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-unsw-nb15-v2 R3.1 xgboost r=0.5 j=0.0 recalibrated dTPR | 15 | -0.04528 | [-0.06782, -0.02274] | -4.31 | 0.000723 | <0.0001 | t:rej / perm:rej | reported |
| nf-unsw-nb15-v2 R3.1 xgboost r=0.5 j=0.7 fixed dFPR | 15 | -0.0143 | [-0.02912, 0.0005106] | -2.07 | 0.0573 | 0.0597 | t:no / perm:no | reported |
| nf-unsw-nb15-v2 R3.1 xgboost r=0.5 j=0.7 recalibrated dTPR | 15 | -0.01318 | [-0.02911, 0.002753] | -1.77 | 0.0978 | 0.0913 | t:no / perm:no | reported |
| nf-unsw-nb15-v2 R3.2 a1 (j=0.7) | 15 | -0.01204 | [-0.03052, 0.006436] | -1.40 | 0.184 | 0.1855 | Bonf α/4: no | a1 fails α/4 |
| nf-unsw-nb15-v2 R3.2 a1truth (j=0.7) | 15 | 0.02135 | [-0.001597, 0.04429] | 2.00 | 0.0658 | 0.065 | Bonf α/4: no | CI includes 0 |
| nf-unsw-nb15-v2 R3.2 s0j (j=0.7) | 15 | -0.01865 | [-0.03726, -4.1e-05] | -2.15 | 0.0496 | 0.0471 | Bonf α/4: no | CI excludes 0 |
| nf-unsw-nb15-v2 R3.2 junk (j=0.0) | 15 | -0.0006814 | [-0.01941, 0.01805] | -0.08 | 0.939 | 0.9445 | Bonf α/4: no | CI includes 0 |
| nf-unsw-nb15-v2 R3.2 secondary a1 − a1truth | 15 | -0.03339 | [-0.05216, -0.01461] | -3.81 | 0.0019 | 0.0033 | — (p<0.05) | negative, p_t<0.05 |
| nf-unsw-nb15-v2 R3.3 rf r=0.2 ShareCap0.05 − none, dFPR | 15 | -0.03671 | [-0.06037, -0.01305] | -3.33 | 0.00498 | 0.0071 | — | R=0.212 [0.094, 0.317] (descr.) |
| nf-unsw-nb15-v2 R3.3 rf r=0.5 ShareCap0.05 − none, dFPR | 15 | -0.09116 | [-0.1136, -0.06877] | -8.73 | 4.88e-07 | <0.0001 | — | R=0.380 [0.310, 0.451] (bar) |
| nf-unsw-nb15-v2 R3.3 xgboost r=0.2 ShareCap0.05 − none, dFPR | 15 | -0.05477 | [-0.07141, -0.03813] | -7.06 | 5.69e-06 | <0.0001 | — | R=0.300 [0.227, 0.378] (descr.) |
| nf-unsw-nb15-v2 R3.3 xgboost r=0.5 ShareCap0.05 − none, dFPR | 15 | -0.1256 | [-0.1511, -0.1002] | -10.58 | 4.62e-08 | <0.0001 | — | R=0.524 [0.443, 0.608] (bar) |
| nf-cse-cic-ids2018-v2 R3.1 rf r=0.2 j=0.0 fixed dFPR | 15 | 0.5182 | [0.4687, 0.5677] | 22.46 | 2.22e-12 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-cse-cic-ids2018-v2 R3.1 rf r=0.2 j=0.0 recalibrated dTPR | 15 | -0.01068 | [-0.01141, -0.009955] | -31.59 | 2.04e-14 | <0.0001 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.1 rf r=0.2 j=0.7 fixed dFPR | 15 | 0.003253 | [0.002492, 0.004014] | 9.17 | 2.7e-07 | <0.0001 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.1 rf r=0.2 j=0.7 recalibrated dTPR | 15 | -0.001941 | [-0.00263, -0.001253] | -6.05 | 3.01e-05 | <0.0001 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.1 rf r=0.5 j=0.0 fixed dFPR | 15 | 0.9687 | [0.9645, 0.9728] | 501.78 | 3.44e-31 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-cse-cic-ids2018-v2 R3.1 rf r=0.5 j=0.0 recalibrated dTPR | 15 | -0.02135 | [-0.0229, -0.01981] | -29.59 | 5.05e-14 | <0.0001 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.1 rf r=0.5 j=0.7 fixed dFPR | 15 | 0.002235 | [0.001593, 0.002877] | 7.47 | 3.01e-06 | 0.0002 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.1 rf r=0.5 j=0.7 recalibrated dTPR | 15 | -0.001659 | [-0.002203, -0.001115] | -6.54 | 1.31e-05 | 0.0001 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.1 xgboost r=0.2 j=0.0 fixed dFPR | 15 | 0.9094 | [0.8964, 0.9224] | 149.78 | 7.69e-24 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-cse-cic-ids2018-v2 R3.1 xgboost r=0.2 j=0.0 recalibrated dTPR | 15 | -0.009781 | [-0.01107, -0.008492] | -16.27 | 1.73e-10 | <0.0001 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.1 xgboost r=0.2 j=0.7 fixed dFPR | 15 | 0.006669 | [0.005286, 0.008051] | 10.35 | 6.12e-08 | <0.0001 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.1 xgboost r=0.2 j=0.7 recalibrated dTPR | 15 | -0.002645 | [-0.003102, -0.002187] | -12.39 | 6.18e-09 | <0.0001 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.1 xgboost r=0.5 j=0.0 fixed dFPR | 15 | 0.9864 | [0.985, 0.9878] | 1540.99 | 5.19e-38 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-cse-cic-ids2018-v2 R3.1 xgboost r=0.5 j=0.0 recalibrated dTPR | 15 | -0.01702 | [-0.018, -0.01603] | -37.18 | 2.14e-15 | <0.0001 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.1 xgboost r=0.5 j=0.7 fixed dFPR | 15 | 0.007499 | [0.006629, 0.008368] | 18.50 | 3.09e-11 | <0.0001 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.1 xgboost r=0.5 j=0.7 recalibrated dTPR | 15 | -0.006061 | [-0.006752, -0.005369] | -18.81 | 2.47e-11 | <0.0001 | t:rej / perm:rej | reported |
| nf-cse-cic-ids2018-v2 R3.2 a1 (j=0.7) | 15 | -0.001941 | [-0.00263, -0.001253] | -6.05 | 3.01e-05 | <0.0001 | Bonf α/4: both | a1 clears α/4 |
| nf-cse-cic-ids2018-v2 R3.2 a1truth (j=0.7) | 15 | 0.001083 | [0.0003731, 0.001794] | 3.27 | 0.00557 | 0.0046 | Bonf α/4: both | CI excludes 0 |
| nf-cse-cic-ids2018-v2 R3.2 s0j (j=0.7) | 15 | -0.002189 | [-0.002767, -0.001612] | -8.14 | 1.13e-06 | <0.0001 | Bonf α/4: both | CI excludes 0 |
| nf-cse-cic-ids2018-v2 R3.2 junk (j=0.0) | 15 | -0.00161 | [-0.002105, -0.001115] | -6.97 | 6.52e-06 | <0.0001 | Bonf α/4: both | CI excludes 0 |
| nf-cse-cic-ids2018-v2 R3.2 secondary a1 − a1truth | 15 | -0.003025 | [-0.003654, -0.002396] | -10.31 | 6.36e-08 | <0.0001 | — (p<0.05) | negative, p_t<0.05 |
| nf-cse-cic-ids2018-v2 R3.3 rf r=0.2 ShareCap0.05 − none, dFPR | 15 | -0.498 | [-0.5441, -0.452] | -23.20 | 1.43e-12 | <0.0001 | — | R=0.961 [0.957, 0.965] (descr.) |
| nf-cse-cic-ids2018-v2 R3.3 rf r=0.5 ShareCap0.05 − none, dFPR | 15 | -0.9386 | [-0.9413, -0.9359] | -751.31 | 1.21e-33 | <0.0001 | — | R=0.969 [0.964, 0.973] (bar) |
| nf-cse-cic-ids2018-v2 R3.3 xgboost r=0.2 ShareCap0.05 − none, dFPR | 15 | -0.8721 | [-0.8828, -0.8613] | -174.10 | 9.37e-25 | <0.0001 | — | R=0.959 [0.955, 0.963] (descr.) |
| nf-cse-cic-ids2018-v2 R3.3 xgboost r=0.5 ShareCap0.05 − none, dFPR | 15 | -0.9465 | [-0.9519, -0.9412] | -382.39 | 1.54e-29 | <0.0001 | — | R=0.960 [0.956, 0.963] (bar) |
| nf-ton-iot-v2 R3.1 rf r=0.2 j=0.0 fixed dFPR | 15 | 0.2418 | [0.237, 0.2466] | 107.99 | 7.47e-22 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-ton-iot-v2 R3.1 rf r=0.2 j=0.0 recalibrated dTPR | 15 | -0.6409 | [-0.6634, -0.6184] | -61.03 | 2.17e-18 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.1 rf r=0.2 j=0.7 fixed dFPR | 15 | 0.1591 | [0.1507, 0.1674] | 40.77 | 5.97e-16 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.1 rf r=0.2 j=0.7 recalibrated dTPR | 15 | -0.5968 | [-0.6459, -0.5477] | -26.08 | 2.87e-13 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.1 rf r=0.5 j=0.0 fixed dFPR | 15 | 0.2701 | [0.2669, 0.2734] | 179.31 | 6.2e-25 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-ton-iot-v2 R3.1 rf r=0.5 j=0.0 recalibrated dTPR | 15 | -0.6487 | [-0.6663, -0.6311] | -79.18 | 5.72e-20 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.1 rf r=0.5 j=0.7 fixed dFPR | 15 | 0.1473 | [0.1347, 0.16] | 24.95 | 5.28e-13 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.1 rf r=0.5 j=0.7 recalibrated dTPR | 15 | -0.5708 | [-0.6454, -0.4963] | -16.42 | 1.53e-10 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.1 xgboost r=0.2 j=0.0 fixed dFPR | 15 | 0.2483 | [0.2433, 0.2533] | 107.27 | 8.2e-22 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-ton-iot-v2 R3.1 xgboost r=0.2 j=0.0 recalibrated dTPR | 15 | -0.6202 | [-0.6424, -0.598] | -59.84 | 2.85e-18 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.1 xgboost r=0.2 j=0.7 fixed dFPR | 15 | 0.1431 | [0.1341, 0.1521] | 33.97 | 7.49e-15 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.1 xgboost r=0.2 j=0.7 recalibrated dTPR | 15 | -0.2634 | [-0.2979, -0.2289] | -16.38 | 1.58e-10 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.1 xgboost r=0.5 j=0.0 fixed dFPR | 15 | 0.2754 | [0.2717, 0.279] | 161.58 | 2.66e-24 | <0.0001 | t:rej / perm:rej | bar cell: clears |
| nf-ton-iot-v2 R3.1 xgboost r=0.5 j=0.0 recalibrated dTPR | 15 | -0.6305 | [-0.6519, -0.609] | -63.05 | 1.37e-18 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.1 xgboost r=0.5 j=0.7 fixed dFPR | 15 | 0.1503 | [0.1322, 0.1684] | 17.82 | 5.1e-11 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.1 xgboost r=0.5 j=0.7 recalibrated dTPR | 15 | -0.2925 | [-0.3388, -0.2461] | -13.53 | 1.98e-09 | <0.0001 | t:rej / perm:rej | reported |
| nf-ton-iot-v2 R3.2 a1 (j=0.7) | 15 | -0.5968 | [-0.6459, -0.5477] | -26.08 | 2.87e-13 | <0.0001 | Bonf α/4: both | a1 clears α/4 |
| nf-ton-iot-v2 R3.2 a1truth (j=0.7) | 15 | 0.07301 | [0.05136, 0.09466] | 7.23 | 4.35e-06 | 0.0001 | Bonf α/4: both | CI excludes 0 |
| nf-ton-iot-v2 R3.2 s0j (j=0.7) | 15 | -0.6084 | [-0.6679, -0.5488] | -21.91 | 3.11e-12 | <0.0001 | Bonf α/4: both | CI excludes 0 |
| nf-ton-iot-v2 R3.2 junk (j=0.0) | 15 | -0.4873 | [-0.583, -0.3916] | -10.92 | 3.09e-08 | <0.0001 | Bonf α/4: both | CI excludes 0 |
| nf-ton-iot-v2 R3.2 secondary a1 − a1truth | 15 | -0.6698 | [-0.7173, -0.6223] | -30.26 | 3.7e-14 | <0.0001 | — (p<0.05) | negative, p_t<0.05 |
| nf-ton-iot-v2 R3.3 rf r=0.2 ShareCap0.05 − none, dFPR | 15 | -0.04804 | [-0.05275, -0.04333] | -21.87 | 3.2e-12 | <0.0001 | — | R=0.199 [0.182, 0.216] (descr.) |
| nf-ton-iot-v2 R3.3 rf r=0.5 ShareCap0.05 − none, dFPR | 15 | -0.06096 | [-0.06414, -0.05778] | -41.13 | 5.27e-16 | <0.0001 | — | R=0.226 [0.215, 0.237] (bar) |
| nf-ton-iot-v2 R3.3 xgboost r=0.2 ShareCap0.05 − none, dFPR | 15 | -0.05304 | [-0.05562, -0.05047] | -44.13 | 1.98e-16 | <0.0001 | — | R=0.214 [0.204, 0.223] (descr.) |
| nf-ton-iot-v2 R3.3 xgboost r=0.5 ShareCap0.05 − none, dFPR | 15 | -0.08224 | [-0.08532, -0.07917] | -57.42 | 5.07e-18 | <0.0001 | — | R=0.299 [0.287, 0.309] (bar) |

**R3.1 (per dataset and model).** Bar: "copy-fidelity damage holds" iff both jitter-0
fixed-$\Delta$FPR cells clear Holm (positive); "does not hold" iff neither does; "mixed" iff one
does. **Holds** for RF and XGBoost on all three datasets: all six (dataset, model) pairs have both
bar cells clearing Holm in the positive direction.

**R3.2 primary (per dataset).** Bar: "holds" iff a1 clears $\alpha/4$ by both tests and every null
arm's 95% CI includes 0; "does not hold" iff a1 fails $\alpha/4$; "mixed" otherwise.
NF-UNSW-NB15-v2: **does not hold** (a1 p_t 0.18). NF-CSE-CIC-IDS2018-v2: **mixed** (a1 clears; no
null arm's CI includes 0). NF-ToN-IoT-v2: **mixed** (a1 clears; no null arm's CI includes 0).

**R3.2 secondary (per dataset).** Bar: "The label conflict does damage beyond the rows themselves"
iff that contrast is negative with paired-$t$ $p<0.05$. **Met** on all three (p_t 0.0019, 6e-8,
4e-14). Reported next to the primary bar, not in place of it.

**R3.3 (per dataset and model).** Bar: "holds" iff $R\ge0.90$; "does not hold" otherwise; "not
evaluable" iff R3.1's ratio-0.5 jitter-0 $\Delta$FPR does not clear Holm. All six pairs are
evaluable. NF-CSE-CIC-IDS2018-v2: **holds** (RF 0.969, XGBoost 0.960). NF-UNSW-NB15-v2: **does
not hold** (RF 0.380, XGBoost 0.524). NF-ToN-IoT-v2: **does not hold** (RF 0.226, XGBoost 0.299).
