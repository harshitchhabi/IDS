# Phase 0: synthetic vs. real CICIDS2017

Same code, same configs, same seeds. `--source synthetic` vs `--source cicids`
(the real `MachineLearningCVE` CSVs, ~2.83M flows). The methodology-section
comparison: which Phase 0 results are real and which were synthetic artifacts.

## Scale and cleaning

| | synthetic | CICIDS2017 |
|---|---:|---:|
| raw rows | ~112,000 | 2,830,743 |
| dropped: exact duplicates | ~600 | 765,038 (**27%**) |
| dropped: NaN / +-Inf rate cells | ~500 | 2,867 |
| dropped: negative Flow Duration | ~70 | 2,890 |
| **cleaned rows** | ~110,000 | 2,059,948 |
| guard (a) near-duplicates removed | ~750 (injected fingerprints, 0 benign) | 1,011,281 (**49% of cleaned**; ~850k benign) |

CICIDS2017 `MachineLearningCVE` has **no `Timestamp` column** — the within-day
split sorts by row order. Its exact-duplicate rate (27%) is the documented
gotcha; the near-duplicate rate (a further 49%) is new information: real benign
web traffic and real DoS floods are extremely self-similar in 24 flow-summary
features. The grid sweep (`grid_sweep.csv`, `docs/DECISIONS.md` §11) shows model
metrics are insensitive to how aggressively this is done.

## Partition strategies (after the per-(day,family) split fix)

| | synthetic `within_day` | CICIDS `within_day` | CICIDS `day_split` |
|---|---|---|---|
| **attack-class leak_warning** | **false** (NN p5 = 0.44) | **true** (NN p5 = **0.003**) | **false** (NN p5 = **0.65**) |
| every family in every partition | yes | yes (all 13 attack families `seen_both`) | no — day-disjoint by construction |
| eval-family arms populated | all four (via explicit withholding config) | `seen_both` only (+ 1 tiny `seed_only` split artifact) | `novel` only |
| reportable eval families (≥500 rows) | 8 | 3 (DoS Hulk, DDoS, DoS GoldenEye) | 3 (DDoS, PortScan, Bot) |
| usable for S0? | **yes** | no — leaks on DoS degeneracy | yes, but tests cross-family generalization |

The per-(day,family) split fixed the bucket-assignment bug (whole families were
landing in single partitions). But it does not fix feature-space degeneracy:
under `within_day`, real DoS bursts' early and late flows are near-identical, so
the guard still fires. `day_split` — genuinely different days and families — is
leak-free once the benign class stops gating the warning.

## Models — trusted_eval, fixed threshold (target FPR 1%)

### synthetic `within_day` (4 arms, all populated by explicit withholding)

| model | eval FPR / TPR | AUROC | seen_both | seed_only (A4) | honeypot_only | novel |
|---|---|---:|---:|---:|---:|---:|
| RF | 0.008 / 0.77 | 0.947 | 0.95 | 1.00 | **0.43** | 0.007 |
| XGBoost | 0.008 / 0.76 | 0.951 | 0.95 | 1.00 | **0.35** | 0.007 |
| autoencoder | 0.010 / 0.52 | 0.910 | 0.52 | 0.28 | **0.99** | 0.26 |

`honeypot_only` (DoS Hulk, withheld from seed_train) is the arm the loop should
move: RF sees only 43% of it without the honeypot's data. The autoencoder, being
benign-only, already catches it (99%) and misses the subtle families.

### CICIDS `within_day` — **leak_warning is set (attack NN p5 = 0.003); memorization**

| model | eval FPR / TPR | AUROC | DoS Hulk (12k) | DDoS (8k) | DoS GoldenEye (3k) |
|---|---|---:|---:|---:|---:|
| RF (fixed) | 0.040 / 0.96 | 0.997 | 0.93 | 1.00 | 1.00 |
| RF (recal) | 0.010 / 0.94 | 0.997 | 0.89 | 1.00 | 0.99 |
| XGBoost (fixed) | 0.011 / 0.97 | 0.999 | 0.97 | 1.00 | 0.93 |
| autoencoder (fixed) | 0.011 / 0.064 | 0.893 | 0.04 | 0.13 | 0.00 |

Only the 3 DoS/DDoS variants have ≥500 trusted_eval rows. FTP-Patator lands
`seed_only` with 5 eval rows — a split artifact (`arm_source = artifact`), not
reportable.

### CICIDS `day_split` — leak-free (attack NN p5 = 0.65); every family `novel`

| model | eval FPR / TPR | AUROC | Bot (583) | DDoS (59k) | PortScan (1.1k) |
|---|---|---:|---:|---:|---:|
| RF (fixed) | 0.053 / 0.90 | 0.949 | **0.08** | 0.91 | 0.84 |
| RF (recal) | 0.013 / 0.97 | 0.949 | 0.05 | 0.90 | 0.78 |
| XGBoost (fixed) | 0.003 / 0.65 | 0.970 | 0.05 | 0.66 | 0.33 |
| autoencoder (fixed) | 0.067 / 0.24 | 0.894 | 0.08 | 0.24 | 0.08 |

## Reading the table

- **`tpr_novel` was a synthetic artifact.** Synthetic put every family at a
  parametric shift of one benign profile, so "novel" families still scored
  ~0.5. On real leak-free data (`day_split`): a subtle novel family (Bot, a C2
  beacon) scores **0.05–0.08** — supervised flow classifiers genuinely cannot
  catch it — while volumetric novel families (DDoS) score 0.66–0.91 because any
  attack training teaches "not benign-shaped".
- **A4's `seed_only` arm cannot occur naturally on CICIDS2017** — one family per
  day. It has to be set with `pool_withheld_families`, and only families with
  enough rows survive to be measurable (the 3 DoS/DDoS variants).
- **`honeypot_only`** — the loop's own teaching signal — exists only on
  synthetic here; on `day_split` CICIDS every family is `novel`, on `within_day`
  every family is `seen_both`.
- **Both threshold modes matter more on real data:** RF `eval_fpr` under `fixed`
  is 0.040 (`within_day`) / 0.053 (`day_split`) vs 0.01 recalibrated; on
  synthetic the gap is < 0.003.
- **The autoencoder** ranks attacks (AUROC 0.89–0.91) but its heavy benign
  reconstruction-error tail means a 1% FPR threshold catches almost nothing
  (`eval_tpr` 0.06–0.24). Carried as reference AUROC; S0/A1 use RF + XGBoost.
  See `docs/DECISIONS.md` §12.

## Consequence

The loop is built and exercised on **synthetic data** (all four arms, no leak),
with `day_split` CICIDS2017 as a leak-free real-data cross-check on the `novel`
arm. A real-data partition with both a populated `honeypot_only` arm and no
attack-class leak is the open question — see `docs/DECISIONS.md` §13.
