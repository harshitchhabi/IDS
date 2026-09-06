# Phase 0: synthetic vs. real CICIDS2017

Same code, same configs, same seeds. `--source synthetic` vs `--source cicids`
(the real `MachineLearningCVE` CSVs, ~2.83M flows). This is the methodology-
section comparison table: it shows which Phase 0 results are real and which were
synthetic artifacts.

## Scale and cleaning

| | synthetic | CICIDS2017 |
|---|---:|---:|
| raw rows | 37,757 | 2,830,743 |
| dropped: exact duplicates | 553 | 674,038 (24%) |
| dropped: NaN / +-Inf rate cells | 521 | 2,867 |
| dropped: negative Flow Duration | 69 | 2,890 |
| dropped: unparseable timestamp | 0 | 0 (no Timestamp column at all) |
| **cleaned rows** | **36,614** | **2,059,948** |
| guard (a) near-duplicates removed | 163 (0.4%) | 1,011,279 (**49%**) |
| rows into the partition | 36,451 | 1,048,669 |

CICIDS2017's `MachineLearningCVE` CSVs have **no `Timestamp` column**, so
`within_day_temporal` sorts each day by row order — a poor proxy for capture
time, and one that interacts badly with the dataset's one-attack-family-per-day
structure. The exact-duplicate rate (24%) is the documented CICIDS2017 quirk.
The near-duplicate rate (49% on top of that) is new information: real benign web
traffic and real DoS floods are extremely self-similar in 24 flow-summary
features.

## `within_day_temporal`

| | synthetic | CICIDS2017 |
|---|---|---|
| seed_train / prod_benign / honeypot_pool / trusted_eval | 24.6k / 13.1k / 22.1k / 17.6k | 360k / 168k / 328k / 190k |
| **guard (c) leak_warning** | **false** | **true** |
| guard (c) attack 5th-pct RMS | 0.52 | **0.00** (87% of pairs within grid) |
| guard (c) benign 5th-pct RMS | 0.40 | 0.00 |
| eval family `seen_both` | DDoS, DoS Hulk, PortScan, Web Attack BF | SSH-Patator |
| eval family `seed_only` (A4's arm) | SSH-Patator | **(empty)** |
| eval family `novel` | Bot, Infiltration | Heartbleed (n=7) |

| model (fixed thr) | synth eval TPR | synth AUROC | synth novel TPR | CICIDS eval TPR | CICIDS AUROC | CICIDS novel TPR |
|---|---:|---:|---:|---:|---:|---:|
| RF | 0.70 | 0.91 | **0.55** | 0.92 | 0.99 | **0.00** |
| XGBoost | 0.67 | 0.96 | 0.50 | 0.90 | 0.99 | 0.00 |
| autoencoder | 0.64 | 0.95 | 0.66 | 0.00 | 0.59 | 0.00 |

## `day_split` (robustness appendix)

| | synthetic | CICIDS2017 |
|---|---|---|
| **guard (c) leak_warning** | false | **true** (benign-driven; attack p50 = 0.84) |
| eval family `seen_both` / `seed_only` / `novel` | — / — / (day-disjoint by construction) | (empty) / (empty) / Bot, DDoS, PortScan |

| model (fixed thr) | CICIDS eval TPR | CICIDS AUROC | CICIDS novel TPR |
|---|---:|---:|---:|
| RF | 0.90 | 0.95 | **0.90** |
| XGBoost | 0.68 | 0.98 | 0.68 |
| autoencoder | 0.00 | 0.80 | 0.00 |

## Reading the table

- **`tpr_novel` was a synthetic artifact.** Synthetic put every attack family at
  a parametric shift of one benign profile, so "novel" families still landed in
  the region the model had learned (0.5–0.66). On real data it is entirely
  family-dependent: a truly subtle novel family (Heartbleed) scores 0.00, while
  volumetric novel families (DDoS, PortScan under `day_split`) score ~0.90
  because any attack training teaches "not benign-shaped" and they are nowhere
  near benign.
- **`tpr_seed_only` (A4's measurement arm) is unavailable on CICIDS2017** —
  every attack family runs on exactly one day, so nothing can be in seed_train
  and trusted_eval but withheld from the pool.
- **guard (c) fires on real data under both strategies.** Under
  `within_day_temporal` it is a true positive (DoS is a degenerate feature-space
  cluster that a temporal cut cannot hold out). Under `day_split` it fires on
  benign traffic being naturally identical across days — a limitation of a
  feature-level leak test, which for a day-disjoint split should be read as
  attack-class-only.
- **The autoencoder is unusable on real benign traffic** at a 1% FPR operating
  point — its reconstruction-error tail swallows the attacks.
- **Both threshold modes matter more on real data:** RF `eval_fpr` is 0.048
  under `fixed` vs 0.010 under `recalibrated` (0.008 vs 0.010 on synthetic).

## Consequence

The S0 checkpoint cannot yet be validated on either dataset: synthetic makes it
pass trivially, real CICIDS2017 leaks. See `docs/DECISIONS.md` §10.
