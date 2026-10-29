# Phase R item R1 (power): results

**Branch:** `claude/phase-r-session-r1-oxrgw5` (IDS). Pre-registration: `docs/DECISIONS.md` §31.1,
not edited. Statistics: `experiments/phaseR_r1_stats.py`, outputs in `results/phaseR/r1/`
(`stats.md`, `stats.csv`, `r1a_eval_draw_sensitivity.csv`, `r1b_xgboost_fpr_trajectories.csv`).
VM: 4 vCPU Intel Xeon (x86-64, AVX-512), 15 GB, `WORKERS=3`. Every job in
`experiments/run_phaseR_r1.sh` ran unmodified: 570 + 60 + 105.

## 0. Determinism bug found first, and the one code change it led to

The first full run did not reproduce `results/phase0/loop/cicids_recal/` on any compared job, the
controls included. I reported this before reading any statistic (§31.1), and the author chose to
fix the cause and rerun all of R1. That run is archived unanalysed in `results/phaseR/r1_unfixed/`
(R1.a and R1.b complete, R1.c at 158 of 165: a worker restart killed it, and it was superseded
rather than finished). Everything below comes from the rerun.

**Cause.** `dloop.features.normalize.Normalizer` applied `np.log1p` to float32 arrays. numpy
dispatches float32 `log1p` to SIMD code. On this x86 AVX-512 CPU the result is 1 ulp away from
the correctly rounded value for about 4% of inputs (80,244 of 2,000,000 uniform test values). The
author's machine evidently computes it correctly rounded. Guard (a), the near-duplicate grid snap
(`sim/partition.py::_remove_near_duplicates`), floors normalized values onto a 0.005 lattice, so a
handful of rows that sit on a cell boundary land in a different cell. The CSVs and the cleaning
were identical (`cleaning_report.json` matched exactly, as did the near-dup total of 646,199). But
four day/class near-dup counts moved by ±1, the partitions shifted by a few rows (honeypot_pool
benign 344,227 vs. 344,221 published; trusted_eval benign 229,693 vs. 229,695; trusted_eval attack
52,055 vs. 52,054), and every seeded subsample downstream (seed_train, eval, the A1 pool draws)
changed. The published configs record this directly: all 141 CICIDS `config_*.json` under
`results/` carry `a1_poison_source_rows_checked_disjoint_from_eval_benign = 344221`. The first run
had 344227. Disabling numpy's AVX-512 dispatch did not change the result. Computing `log1p` in
float64 and rounding once to float32 restored the published partitions exactly, with every
near-dup count equal.

**Fix (the only change outside `experiments/`).** `src/dloop/features/normalize.py`:
`Normalizer.fit` and `.transform` call `_log1p32(x) = np.log1p(x.astype(float64)).astype(float32)`.
The model scaler goes through the same `Normalizer` every round, so fixing only the cache would not
have been enough. On a platform whose float32 `log1p` is already correctly rounded, the new path
should give the same bits, but **I could not check that on the author's machine.** Please confirm
there before merging that the change leaves Phase 0 / Phase A outputs unchanged. R2 and R3 run on
the same kind of VM and will hit the same divergence unless they carry this commit. The test suite
passes (159 tests).

**Residual non-reproduction, not explained down to a line of code.** After the fix, the RF
controls and 28 of 30 RF R1.c jobs reproduce bit for bit. One XGBoost control (seed 1) also does.
What still differs:

- XGBoost controls for seeds 2-5. For seed 2 the round-0 fixed threshold is 0.329439 vs. 0.329422,
  with identical training inputs (round-0 `val_benign_dropped_frac` equal). So XGBoost's own
  training is not bit-identical across these two platforms. `n_jobs=1`, `hist`, and xgboost 3.4.1
  from `uv.lock` are the same on both. The likely source is compiled float arithmetic (FMA/SIMD) in
  xgboost; I did not confirm it.
- R1.b's A1 cell, seeds 1-5. This follows from the item above.
- Two RF R1.c jobs (seed 4 jitter 0.01 ratio 0.5, seed 5 jitter 0.1 ratio 0.5) differ by at most 7
  confusion counts in intermediate rounds. Earlier tests showed RF at jitter 0 (exact copies of
  pool rows) diverging from round 4 too.

**How much this reaches the pre-registered outcomes:**

- R1.c: the final-round recalibrated ΔTPR for seeds 1-5 is **identical** to the published value in
  all six cells (max abs difference 0).
- R1.b: round-10 fixed FPR for seeds 1-5 is 0.0060 / 0.8233 / 0.6932 / 0.9059 / 0.0065, against
  0.0060 / 0.8233 / 0.6932 / 0.9076 / 0.0065 published. Only seed 4 differs, by 0.0017, and every
  seed keeps its mode. The s25.6 three-decimal table differs in four entries (seed 2 r6 0.739 vs.
  0.737; seed 3 r20 0.801 vs. 0.800; seed 4 r8 0.842 vs. 0.839 and r10 0.906 vs. 0.908).

§31.1 says R1.b's verdict "is not read until it is explained". The explanation above names the
mechanism (XGBoost training differs across platforms on identical inputs) and shows it cannot
change any seed's mode, but it does not reduce it to a line of code. I report R1.b's verdict on
that basis. Whether this counts as "explained" is a call for the author.

## 1. Check 1: reproduction (R1.b, R1.c seeds 1-5 vs. published cicids_recal)

| job | rounds x modes | published | max abs diff | identical |
|---|---:|---|---:|---|
| a1_xgboost_s1_j0.0_r0.5_vt0.1.csv | 42 | present | 229 | **NO** |
| a1_xgboost_s2_j0.0_r0.5_vt0.1.csv | 42 | present | 503 | **NO** |
| a1_xgboost_s3_j0.0_r0.5_vt0.1.csv | 42 | present | 420 | **NO** |
| a1_xgboost_s4_j0.0_r0.5_vt0.1.csv | 42 | present | 290 | **NO** |
| a1_xgboost_s5_j0.0_r0.5_vt0.1.csv | 42 | present | 470 | **NO** |
| a1_rf_s1_j0.01_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s2_j0.01_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s3_j0.01_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s4_j0.01_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s5_j0.01_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s1_j0.01_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s2_j0.01_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s3_j0.01_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s4_j0.01_r0.5_vt0.1.csv | 42 | present | 7 | **NO** |
| a1_rf_s5_j0.01_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s1_j0.03_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s2_j0.03_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s3_j0.03_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s4_j0.03_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s5_j0.03_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s1_j0.03_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s2_j0.03_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s3_j0.03_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s4_j0.03_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s5_j0.03_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s1_j0.1_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s2_j0.1_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s3_j0.1_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s4_j0.1_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s5_j0.1_r0.2_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s1_j0.1_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s2_j0.1_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s3_j0.1_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s4_j0.1_r0.5_vt0.1.csv | 42 | present | 0 | yes |
| a1_rf_s5_j0.1_r0.5_vt0.1.csv | 42 | present | 1 | **NO** |
| control_rf_s1_j0.0_r0.0_vt0.1.csv | 42 | present | 0 | yes |
| control_rf_s2_j0.0_r0.0_vt0.1.csv | 42 | present | 0 | yes |
| control_rf_s3_j0.0_r0.0_vt0.1.csv | 42 | present | 0 | yes |
| control_rf_s4_j0.0_r0.0_vt0.1.csv | 42 | present | 0 | yes |
| control_rf_s5_j0.0_r0.0_vt0.1.csv | 42 | present | 0 | yes |
| control_xgboost_s1_j0.0_r0.0_vt0.1.csv | 42 | present | 0 | yes |
| control_xgboost_s2_j0.0_r0.0_vt0.1.csv | 42 | present | 232 | **NO** |
| control_xgboost_s3_j0.0_r0.0_vt0.1.csv | 42 | present | 94 | **NO** |
| control_xgboost_s4_j0.0_r0.0_vt0.1.csv | 42 | present | 27 | **NO** |
| control_xgboost_s5_j0.0_r0.0_vt0.1.csv | 42 | present | 112 | **NO** |

**Reproduction: mismatch on 11 of 45 jobs (all 5 R1.b A1 jobs, XGBoost controls 2-5, RF R1.c seed 4 j0.01 r0.5 and seed 5 j0.1 r0.5). Cause and extent: §0. The pre-registered outcomes for R1.c seeds 1-5 are identical; R1.b differs only at seed 4 (round-10 FPR 0.9059 vs. 0.9076).**

## 2. Check 2: pairing (R1.a, `_evr` A1 vs. same-seed `_evr` control)

- A1 `_evr` jobs checked: 540; mismatches: 0
- redraw took effect: of 10 seed-1-5 controls, 9 have the published round-0 fixed threshold (same training) and 10 have different eval confusion counts (different eval rows)

**Pairing: all equal.**

## 3. R1.a: 36-cell grid, 15 seeds, eval redrawn per seed

| cell (model, ratio, jitter) | n | mean ΔTPR | 95% CI | t | p_t | p_perm | Holm thr | n=15 Holm (p_t) | n=15 Holm (p_perm) | n=5 mean | n=5 t | n=5 status |
|---|---:|---:|---|---:|---:|---:|---:|---|---|---:|---:|---|
| rf, 0.5, 0.0 | 15 | -0.2982 | [-0.3176, -0.2788] | -32.99 | 1.12e-14 | <0.0001 | 0.00139 | clears (neg) | clears (neg) | -0.2817 | -16.57 | clears (neg) |
| xgboost, 0.5, 0.0 | 15 | -0.2269 | [-0.2547, -0.1991] | -17.52 | 6.43e-11 | <0.0001 | 0.00143 | clears (neg) | clears (neg) | -0.2187 | -8.49 | clears (neg) |
| rf, 0.2, 0.0 | 15 | -0.1575 | [-0.1821, -0.1330] | -13.76 | 1.59e-09 | <0.0001 | 0.00147 | clears (neg) | clears (neg) | -0.1399 | -20.32 | clears (neg) |
| xgboost, 0.2, 0.01 | 15 | +0.0680 | [+0.0572, +0.0787] | +13.56 | 1.93e-09 | <0.0001 | 0.00152 | survives, positive (not counted) | survives, positive (not counted) | +0.0732 | +7.15 | no |
| rf, 0.5, 1.5 | 15 | -0.1134 | [-0.1315, -0.0952] | -13.39 | 2.26e-09 | <0.0001 | 0.00156 | clears (neg) | clears (neg) | -0.0953 | -6.95 | no |
| xgboost, 0.2, 0.03 | 15 | +0.0688 | [+0.0573, +0.0804] | +12.80 | 4.09e-09 | <0.0001 | 0.00161 | survives, positive (not counted) | survives, positive (not counted) | +0.0769 | +7.35 | no |
| rf, 0.2, 1.5 | 15 | -0.1143 | [-0.1368, -0.0919] | -10.93 | 3.07e-08 | <0.0001 | 0.00167 | clears (neg) | clears (neg) | -0.1033 | -6.02 | no |
| rf, 0.2, 0.7 | 15 | -0.1238 | [-0.1491, -0.0985] | -10.50 | 5.1e-08 | <0.0001 | 0.00172 | clears (neg) | clears (neg) | -0.1090 | -6.34 | no |
| xgboost, 0.2, 0.002 | 15 | +0.0684 | [+0.0533, +0.0835] | +9.73 | 1.3e-07 | <0.0001 | 0.00179 | survives, positive (not counted) | survives, positive (not counted) | +0.0761 | +5.62 | no |
| xgboost, 0.2, 0.005 | 15 | +0.0597 | [+0.0432, +0.0762] | +7.77 | 1.92e-06 | <0.0001 | 0.00185 | survives, positive (not counted) | survives, positive (not counted) | +0.0641 | +3.68 | no |
| xgboost, 0.2, 0.3 | 15 | +0.0371 | [+0.0262, +0.0480] | +7.30 | 3.89e-06 | <0.0001 | 0.00192 | survives, positive (not counted) | survives, positive (not counted) | +0.0409 | +5.91 | no |
| xgboost, 0.2, 0.0 | 15 | -0.0643 | [-0.0836, -0.0449] | -7.11 | 5.22e-06 | <0.0001 | 0.00200 | clears (neg) | clears (neg) | -0.0599 | -2.58 | no |
| xgboost, 0.2, 0.1 | 15 | +0.0428 | [+0.0292, +0.0564] | +6.73 | 9.57e-06 | <0.0001 | 0.00208 | survives, positive (not counted) | survives, positive (not counted) | +0.0421 | +3.97 | no |
| rf, 0.5, 0.7 | 15 | -0.1279 | [-0.1700, -0.0858] | -6.52 | 1.36e-05 | <0.0001 | 0.00217 | clears (neg) | clears (neg) | -0.1189 | -3.24 | no |
| rf, 0.2, 0.3 | 15 | -0.0997 | [-0.1334, -0.0660] | -6.35 | 1.8e-05 | 0.0001 | 0.00227 | clears (neg) | clears (neg) | -0.0736 | -3.62 | no |
| rf, 0.5, 0.002 | 15 | -0.0340 | [-0.0561, -0.0118] | -3.29 | 0.00539 | 0.0085 | 0.00238 | no | no | -0.0007 | -0.06 | no |
| rf, 0.5, 0.3 | 15 | -0.0472 | [-0.0783, -0.0162] | -3.26 | 0.00571 | 0.0023 | 0.00250 | no | clears (neg) | -0.0159 | -1.59 | no |
| xgboost, 0.5, 0.1 | 15 | +0.0226 | [+0.0043, +0.0410] | +2.65 | 0.0191 | 0.0205 | 0.00263 | no | no | +0.0271 | +1.87 | no |
| rf, 0.5, 0.01 | 15 | -0.0262 | [-0.0495, -0.0029] | -2.41 | 0.03 | 0.0318 | 0.00278 | no | no | +0.0096 | +0.51 | no |
| rf, 0.5, 0.1 | 15 | -0.0394 | [-0.0763, -0.0025] | -2.29 | 0.0379 | 0.0366 | 0.00294 | no | no | +0.0153 | +1.35 | no |
| rf, 0.2, 0.1 | 15 | -0.0433 | [-0.0858, -0.0007] | -2.18 | 0.0466 | 0.0414 | 0.00313 | no | no | -0.0509 | -1.16 | no |
| xgboost, 0.2, 0.7 | 15 | +0.0142 | [-0.0003, +0.0288] | +2.10 | 0.054 | 0.052 | 0.00333 | no | no | +0.0168 | +1.47 | no |
| rf, 0.5, 0.03 | 15 | -0.0251 | [-0.0510, +0.0007] | -2.09 | 0.0554 | 0.0554 | 0.00357 | no | no | +0.0110 | +1.16 | no |
| rf, 0.2, 0.01 | 15 | -0.0332 | [-0.0701, +0.0037] | -1.93 | 0.0743 | 0.0757 | 0.00385 | no | no | -0.0534 | -1.51 | no |
| rf, 0.5, 0.005 | 15 | -0.0205 | [-0.0433, +0.0024] | -1.92 | 0.0751 | 0.0735 | 0.00417 | no | no | +0.0111 | +1.90 | no |
| rf, 0.2, 0.005 | 15 | -0.0232 | [-0.0548, +0.0084] | -1.58 | 0.137 | 0.1265 | 0.00455 | no | no | -0.0241 | -0.89 | no |
| rf, 0.2, 0.002 | 15 | -0.0284 | [-0.0675, +0.0107] | -1.56 | 0.141 | 0.142 | 0.00500 | no | no | -0.0284 | -0.97 | no |
| rf, 0.2, 0.03 | 15 | -0.0246 | [-0.0616, +0.0123] | -1.43 | 0.174 | 0.181 | 0.00556 | no | no | -0.0118 | -0.45 | no |
| xgboost, 0.5, 0.002 | 15 | +0.0102 | [-0.0061, +0.0264] | +1.34 | 0.2 | 0.199 | 0.00625 | no | no | +0.0171 | +2.16 | no |
| xgboost, 0.5, 0.7 | 15 | -0.0073 | [-0.0214, +0.0068] | -1.11 | 0.288 | 0.2915 | 0.00714 | no | no | -0.0010 | -0.10 | no |
| xgboost, 0.5, 0.005 | 15 | +0.0076 | [-0.0072, +0.0224] | +1.10 | 0.29 | 0.2875 | 0.00833 | no | no | +0.0136 | +1.27 | no |
| xgboost, 0.5, 1.5 | 15 | +0.0048 | [-0.0063, +0.0159] | +0.93 | 0.37 | 0.4226 | 0.01000 | no | no | +0.0025 | +0.90 | no |
| xgboost, 0.2, 1.5 | 15 | -0.0038 | [-0.0133, +0.0056] | -0.86 | 0.402 | 0.3923 | 0.01250 | no | no | -0.0071 | -1.29 | no |
| xgboost, 0.5, 0.03 | 15 | -0.0074 | [-0.0292, +0.0145] | -0.72 | 0.481 | 0.4848 | 0.01667 | no | no | -0.0028 | -0.15 | no |
| xgboost, 0.5, 0.01 | 15 | -0.0042 | [-0.0261, +0.0176] | -0.42 | 0.683 | 0.689 | 0.02500 | no | no | +0.0053 | +0.41 | no |
| xgboost, 0.5, 0.3 | 15 | +0.0013 | [-0.0167, +0.0192] | +0.15 | 0.883 | 0.8833 | 0.05000 | no | no | +0.0122 | +0.79 | no |

- Newly clear at n=15 (not at n=5): rf ratio 0.2 jitter 0.3, rf ratio 0.2 jitter 0.7, rf ratio 0.2 jitter 1.5, rf ratio 0.5 jitter 0.7, rf ratio 0.5 jitter 1.5, xgboost ratio 0.2 jitter 0.0
- No longer clear at n=15 (cleared at n=5): none
- Survive Holm in the positive (non-damaging) direction at n=15, not counted: xgboost ratio 0.2 jitter 0.002, xgboost ratio 0.2 jitter 0.005, xgboost ratio 0.2 jitter 0.01, xgboost ratio 0.2 jitter 0.03, xgboost ratio 0.2 jitter 0.1, xgboost ratio 0.2 jitter 0.3
- RF cells at jitter >= 0.3 that clear (consistent with s26.8, not new): rf ratio 0.2 jitter 0.3, rf ratio 0.2 jitter 0.7, rf ratio 0.2 jitter 1.5, rf ratio 0.5 jitter 0.7, rf ratio 0.5 jitter 1.5

**Eval-draw sensitivity (descriptive, not tested).** Seeds 1-5, same cell, published fixed draw vs. this run's per-seed redraw.

| cell | mean Δ fixed | mean Δ redraw | mean abs Δ fixed | mean abs Δ redraw | mean abs(Δfixed − Δredraw) per seed |
|---|---:|---:|---:|---:|---:|
| rf, 0.2, 0.0 | -0.1399 | -0.1353 | 0.1399 | 0.1353 | 0.0063 |
| rf, 0.2, 0.002 | -0.0284 | -0.0267 | 0.0484 | 0.0485 | 0.0021 |
| rf, 0.2, 0.005 | -0.0241 | -0.0227 | 0.0475 | 0.0483 | 0.0025 |
| rf, 0.2, 0.01 | -0.0534 | -0.0495 | 0.0750 | 0.0732 | 0.0050 |
| rf, 0.2, 0.03 | -0.0118 | -0.0096 | 0.0453 | 0.0461 | 0.0027 |
| rf, 0.2, 0.1 | -0.0509 | -0.0475 | 0.0718 | 0.0688 | 0.0034 |
| rf, 0.2, 0.3 | -0.0736 | -0.0728 | 0.0736 | 0.0728 | 0.0022 |
| rf, 0.2, 0.7 | -0.1090 | -0.1074 | 0.1090 | 0.1074 | 0.0018 |
| rf, 0.2, 1.5 | -0.1033 | -0.1013 | 0.1033 | 0.1013 | 0.0035 |
| rf, 0.5, 0.0 | -0.2817 | -0.2807 | 0.2817 | 0.2807 | 0.0016 |
| rf, 0.5, 0.002 | -0.0007 | -0.0072 | 0.0199 | 0.0271 | 0.0130 |
| rf, 0.5, 0.005 | +0.0111 | +0.0156 | 0.0135 | 0.0166 | 0.0049 |
| rf, 0.5, 0.01 | +0.0096 | +0.0105 | 0.0324 | 0.0316 | 0.0028 |
| rf, 0.5, 0.03 | +0.0110 | +0.0108 | 0.0189 | 0.0203 | 0.0024 |
| rf, 0.5, 0.1 | +0.0153 | +0.0194 | 0.0208 | 0.0227 | 0.0041 |
| rf, 0.5, 0.3 | -0.0159 | -0.0138 | 0.0244 | 0.0226 | 0.0024 |
| rf, 0.5, 0.7 | -0.1189 | -0.1174 | 0.1189 | 0.1174 | 0.0024 |
| rf, 0.5, 1.5 | -0.0953 | -0.0961 | 0.0953 | 0.0961 | 0.0034 |
| xgboost, 0.2, 0.0 | -0.0599 | -0.0511 | 0.0599 | 0.0511 | 0.0121 |
| xgboost, 0.2, 0.002 | +0.0761 | +0.0755 | 0.0761 | 0.0755 | 0.0035 |
| xgboost, 0.2, 0.005 | +0.0641 | +0.0600 | 0.0641 | 0.0600 | 0.0041 |
| xgboost, 0.2, 0.01 | +0.0732 | +0.0716 | 0.0732 | 0.0716 | 0.0038 |
| xgboost, 0.2, 0.03 | +0.0769 | +0.0753 | 0.0769 | 0.0753 | 0.0047 |
| xgboost, 0.2, 0.1 | +0.0421 | +0.0432 | 0.0421 | 0.0432 | 0.0018 |
| xgboost, 0.2, 0.3 | +0.0409 | +0.0464 | 0.0409 | 0.0464 | 0.0059 |
| xgboost, 0.2, 0.7 | +0.0168 | +0.0185 | 0.0273 | 0.0290 | 0.0028 |
| xgboost, 0.2, 1.5 | -0.0071 | -0.0046 | 0.0115 | 0.0114 | 0.0037 |
| xgboost, 0.5, 0.0 | -0.2187 | -0.2096 | 0.2187 | 0.2096 | 0.0107 |
| xgboost, 0.5, 0.002 | +0.0171 | +0.0106 | 0.0181 | 0.0136 | 0.0071 |
| xgboost, 0.5, 0.005 | +0.0136 | +0.0104 | 0.0231 | 0.0184 | 0.0065 |
| xgboost, 0.5, 0.01 | +0.0053 | -0.0002 | 0.0231 | 0.0208 | 0.0071 |
| xgboost, 0.5, 0.03 | -0.0028 | -0.0069 | 0.0314 | 0.0289 | 0.0042 |
| xgboost, 0.5, 0.1 | +0.0271 | +0.0311 | 0.0290 | 0.0344 | 0.0083 |
| xgboost, 0.5, 0.3 | +0.0122 | +0.0098 | 0.0246 | 0.0240 | 0.0046 |
| xgboost, 0.5, 0.7 | -0.0010 | +0.0017 | 0.0179 | 0.0206 | 0.0032 |
| xgboost, 0.5, 1.5 | +0.0025 | +0.0025 | 0.0056 | 0.0061 | 0.0032 |

Across the 36 cells: median per-seed abs(Δfixed − Δredraw) 0.0036, max 0.0130; median abs(mean Δ fixed − mean Δ redraw) 0.0022.

R1.a survivors at n=15: {'rf 0.2': True, 'rf 0.5': True, 'xgboost 0.5': True} -> **holds**

## 4. R1.b: XGBoost bimodality, 30 seeds

| seed | r2 | r4 | r6 | r8 | r10 | r12 | r15 | r20 | mode (r10) | control r10 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| 1 | 0.005 | 0.005 | 0.004 | 0.006 | 0.006 | 0.006 | 0.007 | 0.019 | low | 0.000 |
| 2 | 0.016 | 0.503 | 0.739 | 0.782 | 0.823 | 0.878 | 0.924 | 0.955 | high | 0.007 |
| 3 | 0.006 | 0.007 | 0.053 | 0.538 | 0.693 | 0.714 | 0.734 | 0.801 | high | 0.003 |
| 4 | 0.046 | 0.708 | 0.775 | 0.842 | 0.906 | 0.949 | 0.948 | 0.958 | high | 0.016 |
| 5 | 0.005 | 0.004 | 0.004 | 0.006 | 0.007 | 0.008 | 0.010 | 0.117 | low | 0.001 |
| 6 | 0.006 | 0.008 | 0.013 | 0.052 | 0.399 | 0.593 | 0.677 | 0.739 | high | 0.003 |
| 7 | 0.005 | 0.006 | 0.009 | 0.034 | 0.067 | 0.400 | 0.602 | 0.710 | intermediate | 0.002 |
| 8 | 0.663 | 0.845 | 0.937 | 0.996 | 0.974 | 0.982 | 0.977 | 0.974 | high | 0.021 |
| 9 | 0.006 | 0.014 | 0.047 | 0.428 | 0.653 | 0.725 | 0.732 | 0.781 | high | 0.005 |
| 10 | 0.005 | 0.004 | 0.007 | 0.008 | 0.011 | 0.030 | 0.383 | 0.656 | low | 0.002 |
| 11 | 0.531 | 0.772 | 0.891 | 0.938 | 0.968 | 0.972 | 0.971 | 0.971 | high | 0.024 |
| 12 | 0.005 | 0.006 | 0.007 | 0.007 | 0.012 | 0.018 | 0.149 | 0.627 | low | 0.003 |
| 13 | 0.005 | 0.007 | 0.030 | 0.356 | 0.609 | 0.677 | 0.721 | 0.759 | high | 0.003 |
| 14 | 0.006 | 0.006 | 0.037 | 0.336 | 0.594 | 0.670 | 0.735 | 0.758 | high | 0.005 |
| 15 | 0.009 | 0.044 | 0.617 | 0.723 | 0.759 | 0.792 | 0.844 | 0.930 | high | 0.005 |
| 16 | 0.004 | 0.005 | 0.007 | 0.008 | 0.015 | 0.039 | 0.401 | 0.669 | low | 0.004 |
| 17 | 0.006 | 0.095 | 0.594 | 0.735 | 0.763 | 0.780 | 0.845 | 0.935 | high | 0.007 |
| 18 | 0.006 | 0.007 | 0.008 | 0.033 | 0.243 | 0.577 | 0.674 | 0.729 | intermediate | 0.001 |
| 19 | 0.005 | 0.009 | 0.124 | 0.541 | 0.666 | 0.717 | 0.743 | 0.795 | high | 0.005 |
| 20 | 0.005 | 0.005 | 0.006 | 0.009 | 0.015 | 0.036 | 0.255 | 0.642 | low | 0.002 |
| 21 | 0.006 | 0.011 | 0.047 | 0.486 | 0.654 | 0.709 | 0.745 | 0.793 | high | 0.005 |
| 22 | 0.005 | 0.006 | 0.008 | 0.022 | 0.104 | 0.527 | 0.669 | 0.721 | intermediate | 0.003 |
| 23 | 0.006 | 0.006 | 0.008 | 0.020 | 0.036 | 0.319 | 0.619 | 0.707 | low | 0.005 |
| 24 | 0.022 | 0.607 | 0.759 | 0.796 | 0.851 | 0.906 | 0.936 | 0.967 | high | 0.007 |
| 25 | 0.609 | 0.801 | 0.933 | 0.959 | 0.969 | 0.967 | 0.975 | 0.963 | high | 0.013 |
| 26 | 0.008 | 0.012 | 0.109 | 0.616 | 0.728 | 0.757 | 0.788 | 0.858 | high | 0.006 |
| 27 | 0.006 | 0.006 | 0.009 | 0.024 | 0.049 | 0.391 | 0.611 | 0.708 | low | 0.002 |
| 28 | 0.005 | 0.009 | 0.026 | 0.295 | 0.623 | 0.688 | 0.736 | 0.779 | high | 0.005 |
| 29 | 0.006 | 0.016 | 0.099 | 0.575 | 0.698 | 0.746 | 0.774 | 0.822 | high | 0.005 |
| 30 | 0.703 | 0.887 | 0.964 | 0.973 | 0.974 | 0.962 | 0.975 | 0.975 | high | 0.013 |

(Every round 2-20 per seed: `results/phaseR/r1/r1b_xgboost_fpr_trajectories.csv`.)

- Mode counts at round 10 (high > 0.3, low < 0.05, intermediate otherwise): high 19, low 8, intermediate 3
- High-mode share 19/30 = 0.633, Clopper-Pearson 95% CI [0.439, 0.801]
- Intermediate seeds: [7, 18, 22]

R1.b -> **holds**

## 5. R1.c: RF mid-range jitters, 15 seeds

| cell (ratio, jitter) | n | mean ΔTPR | 95% CI | t | p_t | p_perm | Holm thr | Holm (p_t) | Holm (p_perm) |
|---|---:|---:|---|---:|---:|---:|---:|---|---|
| 0.2, 0.01 | 15 | -0.0366 | [-0.0731, -0.0002] | -2.16 | 0.049 | 0.0457 | 0.0167 | no | no |
| 0.2, 0.03 | 15 | -0.0252 | [-0.0591, +0.0088] | -1.59 | 0.134 | 0.1394 | 0.0500 | no | no |
| 0.2, 0.1 | 15 | -0.0443 | [-0.0852, -0.0034] | -2.32 | 0.0357 | 0.0311 | 0.0125 | no | no |
| 0.5, 0.01 | 15 | -0.0290 | [-0.0535, -0.0046] | -2.54 | 0.0234 | 0.0253 | 0.0083 | no | no |
| 0.5, 0.03 | 15 | -0.0260 | [-0.0531, +0.0011] | -2.06 | 0.0589 | 0.0581 | 0.0250 | no | no |
| 0.5, 0.1 | 15 | -0.0410 | [-0.0781, -0.0039] | -2.37 | 0.0326 | 0.03 | 0.0100 | no | no |

R1.c clears: {(0.2, 0.01): False, (0.2, 0.03): False, (0.2, 0.1): False, (0.5, 0.01): False, (0.5, 0.03): False, (0.5, 0.1): False} -> **does not hold**


## Verdicts

Holm runs on the two-sided paired-$t$ $p$ (primary). A cell clears only when it survives Holm with
a negative mean. The Holm-on-$p_{\rm perm}$ column is reported alongside and changes no verdict.

**R1.a — holds.** Bar: *"the s26.1 survivors hold" iff all three s26.1 survivors clear Holm at
$n=15$ in the damaging (negative) direction; "does not hold" iff none of the three does; "mixed"
otherwise.* All three clear at $n=15$ with the eval subsample redrawn per seed: RF ratio 0.2
($t=-13.76$), RF ratio 0.5 ($t=-32.99$), XGBoost ratio 0.5 ($t=-17.52$), all at jitter 0. Six cells
**newly clear**: RF ratio 0.2 at jitter 0.3, 0.7 and 1.5; RF ratio 0.5 at jitter 0.7 and 1.5; and
XGBoost ratio 0.2 at jitter 0 ($-0.064$, $t=-7.11$; $t=-2.58$ at $n=5$). The five RF cells at
jitter $\ge0.3$ are, as the bar requires, reported as **consistent with s26.8, not as a new
finding**. The XGBoost ratio-0.2 jitter-0 cell is the one new cell. **No cell that cleared at
$n=5$ fails at $n=15$.** Six XGBoost ratio-0.2 cells (jitter 0.002-0.3) survive Holm in the
**positive** direction (TPR improves under A1). They are reported, not counted, and they repeat
s26.1's uncorrected positive XGBoost ratio-0.2 pattern, now surviving correction. Eval-draw
sensitivity (descriptive): across the 36 cells the median per-seed |Δ(fixed draw) − Δ(redraw)| over
seeds 1-5 is 0.0036 (max 0.0130, RF ratio 0.5 jitter 0.002), and the median shift in the cell mean
is 0.0022. The fixed eval draw was not driving the s26.1 result.

**R1.b — holds** (read after the §0 explanation). Bar: *"bimodality holds" iff at least 3 of 30
seeds are in the high mode, at least 3 in the low mode, and at most 3 are intermediate; "does not
hold" iff at most 2 seeds are in the high mode or at most 2 in the low mode; "mixed" otherwise
(both modes populated but more than 3 seeds in between).* High 19, low 8, intermediate 3 (seeds 7,
18, 22). High-mode share 0.633, Clopper-Pearson 95% CI [0.439, 0.801]. **This sits exactly on the
"at most 3 intermediate" edge:** one more intermediate seed would make it "mixed". It also comes
with a substantive caveat the bar does not capture. The trajectories show that the low mode at
round 10 is mostly a *delay*, not a separate outcome. Of the 8 low-mode seeds, 6 are above 0.6 FPR
by round 20 (seeds 10, 12, 16, 20, 23, 27). Only seeds 1 (0.019) and 5 (0.117) stay low throughout.
The three intermediate seeds sit on the same rising path a few rounds behind. The round-10 cut
therefore separates "fast" from "slow" onset at least as much as "affected" from "unaffected".
s25.6's reading that XGBoost seeds which "stay below 2% … show no effect at all" holds for 2 of 30
seeds over 20 rounds, not for a third of them.

**R1.c — does not hold.** Bar: *"mid-range damage holds" iff at least two adjacent jitters clear
Holm in the negative direction at both ratios; "does not hold" iff no cell clears Holm in the
negative direction; "mixed" otherwise.* No cell clears Holm. All six means are negative ($-0.025$ to
$-0.044$), and four of six have uncorrected $p_t<0.05$ (smallest 0.023, against a smallest Holm
threshold of 0.0083). On the fixed eval draw the mid range carries a small, consistently negative
RF TPR effect that this family of 6 cannot confirm at 15 seeds. R1.a's redrawn mid-range RF cells
(jitter 0.01-0.1) show the same picture: negative means, none clearing.

## Limitations

- The fix in §0 changes shared code (`src/dloop/features/normalize.py`) and needs checking on the
  author's machine. The residual XGBoost (and occasional RF) cross-platform differences are
  unexplained at the code level.
- R1.a's "n=5 status" column is recomputed from the published (author-platform) jobs with the
  same Holm rule. It reproduces s26.1's three survivors and its $t$ values (e.g. $-20.32$,
  $-16.57$, $-8.49$).
- R1.b's verdict rests on the boundary count of 3 intermediate seeds (see above).

## §6 summary table

R1.a: 36 cells; R1.b: 1 cell; R1.c: 6 cells. Effect = final-round recalibrated ΔTPR (A1 − same-seed
control), except R1.b.

| cell | n | effect | 95% CI | $t$ | $p_t$ | $p_{\rm perm}$ | Holm | vs. §31 bar |
|---|---|---|---|---|---|---|---|---|
| R1.a rf, ratio 0.2, jitter 0 | 15 | ΔTPR -0.1575 | [-0.1821, -0.1330] | -13.76 | 1.59e-09 | <0.0001 | clears (neg) | s26.1 survivor: clears |
| R1.a rf, ratio 0.2, jitter 0.002 | 15 | ΔTPR -0.0284 | [-0.0675, +0.0107] | -1.56 | 0.141 | 0.142 | no | not a survivor |
| R1.a rf, ratio 0.2, jitter 0.005 | 15 | ΔTPR -0.0232 | [-0.0548, +0.0084] | -1.58 | 0.137 | 0.1265 | no | not a survivor |
| R1.a rf, ratio 0.2, jitter 0.01 | 15 | ΔTPR -0.0332 | [-0.0701, +0.0037] | -1.93 | 0.0743 | 0.0757 | no | not a survivor |
| R1.a rf, ratio 0.2, jitter 0.03 | 15 | ΔTPR -0.0246 | [-0.0616, +0.0123] | -1.43 | 0.174 | 0.181 | no | not a survivor |
| R1.a rf, ratio 0.2, jitter 0.1 | 15 | ΔTPR -0.0433 | [-0.0858, -0.0007] | -2.18 | 0.0466 | 0.0414 | no | not a survivor |
| R1.a rf, ratio 0.2, jitter 0.3 | 15 | ΔTPR -0.0997 | [-0.1334, -0.0660] | -6.35 | 1.8e-05 | 0.0001 | clears (neg) | not a survivor; consistent with s26.8 |
| R1.a rf, ratio 0.2, jitter 0.7 | 15 | ΔTPR -0.1238 | [-0.1491, -0.0985] | -10.50 | 5.1e-08 | <0.0001 | clears (neg) | not a survivor; consistent with s26.8 |
| R1.a rf, ratio 0.2, jitter 1.5 | 15 | ΔTPR -0.1143 | [-0.1368, -0.0919] | -10.93 | 3.07e-08 | <0.0001 | clears (neg) | not a survivor; consistent with s26.8 |
| R1.a rf, ratio 0.5, jitter 0 | 15 | ΔTPR -0.2982 | [-0.3176, -0.2788] | -32.99 | 1.12e-14 | <0.0001 | clears (neg) | s26.1 survivor: clears |
| R1.a rf, ratio 0.5, jitter 0.002 | 15 | ΔTPR -0.0340 | [-0.0561, -0.0118] | -3.29 | 0.00539 | 0.0085 | no | not a survivor |
| R1.a rf, ratio 0.5, jitter 0.005 | 15 | ΔTPR -0.0205 | [-0.0433, +0.0024] | -1.92 | 0.0751 | 0.0735 | no | not a survivor |
| R1.a rf, ratio 0.5, jitter 0.01 | 15 | ΔTPR -0.0262 | [-0.0495, -0.0029] | -2.41 | 0.03 | 0.0318 | no | not a survivor |
| R1.a rf, ratio 0.5, jitter 0.03 | 15 | ΔTPR -0.0251 | [-0.0510, +0.0007] | -2.09 | 0.0554 | 0.0554 | no | not a survivor |
| R1.a rf, ratio 0.5, jitter 0.1 | 15 | ΔTPR -0.0394 | [-0.0763, -0.0025] | -2.29 | 0.0379 | 0.0366 | no | not a survivor |
| R1.a rf, ratio 0.5, jitter 0.3 | 15 | ΔTPR -0.0472 | [-0.0783, -0.0162] | -3.26 | 0.00571 | 0.0023 | no | not a survivor |
| R1.a rf, ratio 0.5, jitter 0.7 | 15 | ΔTPR -0.1279 | [-0.1700, -0.0858] | -6.52 | 1.36e-05 | <0.0001 | clears (neg) | not a survivor; consistent with s26.8 |
| R1.a rf, ratio 0.5, jitter 1.5 | 15 | ΔTPR -0.1134 | [-0.1315, -0.0952] | -13.39 | 2.26e-09 | <0.0001 | clears (neg) | not a survivor; consistent with s26.8 |
| R1.a xgboost, ratio 0.2, jitter 0 | 15 | ΔTPR -0.0643 | [-0.0836, -0.0449] | -7.11 | 5.22e-06 | <0.0001 | clears (neg) | not a survivor; newly clears |
| R1.a xgboost, ratio 0.2, jitter 0.002 | 15 | ΔTPR +0.0684 | [+0.0533, +0.0835] | +9.73 | 1.3e-07 | <0.0001 | survives, positive | not a survivor |
| R1.a xgboost, ratio 0.2, jitter 0.005 | 15 | ΔTPR +0.0597 | [+0.0432, +0.0762] | +7.77 | 1.92e-06 | <0.0001 | survives, positive | not a survivor |
| R1.a xgboost, ratio 0.2, jitter 0.01 | 15 | ΔTPR +0.0680 | [+0.0572, +0.0787] | +13.56 | 1.93e-09 | <0.0001 | survives, positive | not a survivor |
| R1.a xgboost, ratio 0.2, jitter 0.03 | 15 | ΔTPR +0.0688 | [+0.0573, +0.0804] | +12.80 | 4.09e-09 | <0.0001 | survives, positive | not a survivor |
| R1.a xgboost, ratio 0.2, jitter 0.1 | 15 | ΔTPR +0.0428 | [+0.0292, +0.0564] | +6.73 | 9.57e-06 | <0.0001 | survives, positive | not a survivor |
| R1.a xgboost, ratio 0.2, jitter 0.3 | 15 | ΔTPR +0.0371 | [+0.0262, +0.0480] | +7.30 | 3.89e-06 | <0.0001 | survives, positive | not a survivor |
| R1.a xgboost, ratio 0.2, jitter 0.7 | 15 | ΔTPR +0.0142 | [-0.0003, +0.0288] | +2.10 | 0.054 | 0.052 | no | not a survivor |
| R1.a xgboost, ratio 0.2, jitter 1.5 | 15 | ΔTPR -0.0038 | [-0.0133, +0.0056] | -0.86 | 0.402 | 0.3923 | no | not a survivor |
| R1.a xgboost, ratio 0.5, jitter 0 | 15 | ΔTPR -0.2269 | [-0.2547, -0.1991] | -17.52 | 6.43e-11 | <0.0001 | clears (neg) | s26.1 survivor: clears |
| R1.a xgboost, ratio 0.5, jitter 0.002 | 15 | ΔTPR +0.0102 | [-0.0061, +0.0264] | +1.34 | 0.2 | 0.199 | no | not a survivor |
| R1.a xgboost, ratio 0.5, jitter 0.005 | 15 | ΔTPR +0.0076 | [-0.0072, +0.0224] | +1.10 | 0.29 | 0.2875 | no | not a survivor |
| R1.a xgboost, ratio 0.5, jitter 0.01 | 15 | ΔTPR -0.0042 | [-0.0261, +0.0176] | -0.42 | 0.683 | 0.689 | no | not a survivor |
| R1.a xgboost, ratio 0.5, jitter 0.03 | 15 | ΔTPR -0.0074 | [-0.0292, +0.0145] | -0.72 | 0.481 | 0.4848 | no | not a survivor |
| R1.a xgboost, ratio 0.5, jitter 0.1 | 15 | ΔTPR +0.0226 | [+0.0043, +0.0410] | +2.65 | 0.0191 | 0.0205 | no | not a survivor |
| R1.a xgboost, ratio 0.5, jitter 0.3 | 15 | ΔTPR +0.0013 | [-0.0167, +0.0192] | +0.15 | 0.883 | 0.8833 | no | not a survivor |
| R1.a xgboost, ratio 0.5, jitter 0.7 | 15 | ΔTPR -0.0073 | [-0.0214, +0.0068] | -1.11 | 0.288 | 0.2915 | no | not a survivor |
| R1.a xgboost, ratio 0.5, jitter 1.5 | 15 | ΔTPR +0.0048 | [-0.0063, +0.0159] | +0.93 | 0.37 | 0.4226 | no | not a survivor |
| R1.b xgboost, ratio 0.5, jitter 0, fixed FPR at round 10 | 30 | high-mode share 19/30 = 0.633 (high 19, low 8, intermediate 3) | [0.439, 0.801] (Clopper-Pearson) | — | — | — | n/a | holds (3 intermediate, at the limit) |
| R1.c rf, ratio 0.2, jitter 0.01 | 15 | ΔTPR -0.0366 | [-0.0731, -0.0002] | -2.16 | 0.049 | 0.0457 | no | does not clear |
| R1.c rf, ratio 0.2, jitter 0.03 | 15 | ΔTPR -0.0252 | [-0.0591, +0.0088] | -1.59 | 0.134 | 0.1394 | no | does not clear |
| R1.c rf, ratio 0.2, jitter 0.1 | 15 | ΔTPR -0.0443 | [-0.0852, -0.0034] | -2.32 | 0.0357 | 0.0311 | no | does not clear |
| R1.c rf, ratio 0.5, jitter 0.01 | 15 | ΔTPR -0.0290 | [-0.0535, -0.0046] | -2.54 | 0.0234 | 0.0253 | no | does not clear |
| R1.c rf, ratio 0.5, jitter 0.03 | 15 | ΔTPR -0.0260 | [-0.0531, +0.0011] | -2.06 | 0.0589 | 0.0581 | no | does not clear |
| R1.c rf, ratio 0.5, jitter 0.1 | 15 | ΔTPR -0.0410 | [-0.0781, -0.0039] | -2.37 | 0.0326 | 0.03 | no | does not clear |

**R1.a: holds.** All three s26.1 survivors clear Holm at n=15 in the negative direction.
**R1.b: holds.** At least 3 high (19), at least 3 low (8), at most 3 intermediate (3). Read after §0's explanation of the residual seed-1-5 mismatch.
**R1.c: does not hold.** No cell clears Holm in the negative direction.
