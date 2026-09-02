# Phase 0 partitions

Strategy `day_split`, config hash `8c4a4cbb5bcea854`. Reviewable without re-running; regenerate with `make phase0-explore`.

## Row counts per partition / class

| partition     |   rows |   benign |   attack |   attack_frac | days           | classes                                    |
|:--------------|-------:|---------:|---------:|--------------:|:---------------|:-------------------------------------------|
| seed_train    |  30311 |    27549 |     2762 |        0.0911 | monday,tuesday | BENIGN,FTP-Patator,SSH-Patator             |
| prod_benign   |  13773 |    13773 |        0 |        0      | wednesday      | BENIGN                                     |
| honeypot_pool |  16534 |    13792 |     2742 |        0.1658 | thursday       | BENIGN,Infiltration,Web Attack Brute Force |
| trusted_eval  |  17913 |    13777 |     4136 |        0.2309 | friday         | BENIGN,Bot,DDoS,PortScan                   |

## Row counts per partition / day / class

|                               |   attack |   benign |
|:------------------------------|---------:|---------:|
| ('honeypot_pool', 'thursday') |     2742 |    13792 |
| ('prod_benign', 'wednesday')  |        0 |    13773 |
| ('seed_train', 'monday')      |        0 |    13778 |
| ('seed_train', 'tuesday')     |     2762 |    13771 |
| ('trusted_eval', 'friday')    |     4136 |    13777 |

## Cleaning — rows dropped (CICIDS2017 gotcha list)

| day       |   rows_in |   rows_out_clean |   dropped_nan |   dropped_negative |   dropped_exact_dup |   dropped_bad_ts |   inf_cells_replaced |   near_dups_removed |   imbalance_ratio_out |
|:----------|----------:|-----------------:|--------------:|-------------------:|--------------------:|-----------------:|---------------------:|--------------------:|----------------------:|
| monday    |     14210 |            13778 |           195 |                 27 |                 210 |                0 |                  280 |                   0 |                inf    |
| tuesday   |     17052 |            16533 |           238 |                 34 |                 247 |                0 |                  344 |                   0 |                  4.99 |
| wednesday |     15631 |            15155 |           217 |                 30 |                 229 |                0 |                  312 |                   0 |                  9.97 |
| thursday  |     17052 |            16534 |           238 |                 32 |                 248 |                0 |                  344 |                   0 |                  5.03 |
| friday    |     18473 |            17913 |           255 |                 37 |                 268 |                0 |                  370 |                   0 |                  3.33 |

Drop reasons: whitespace column names, +-Inf in the two rate features (coerced to NaN then dropped), negative Flow Duration artifacts, exact duplicate rows, unparseable timestamps.

## Guard (a) — near-duplicate removal before splitting

Radius-based in normalized feature space (grid `0.02` per-feature RMS). The synthetic generator injects fingerprint-tight bursts into every *sustained* attack family (an automated tool emitting near-byte-identical flows); the guard must clear them or they leak across the temporal cut and let S0 pass by memorization.

_nothing removed_ (guard did not fire — investigate)

## Guard (b) — temporal guard band at internal cuts

Rows within 150s of a cut time dropped so a burst cannot straddle it.

| stream | rows dropped |
|---|---|

## Guard (c) — nearest-neighbour distance, trusted_eval → honeypot_pool

Per-feature RMS distance in normalized space, run for both classes. Concentration near zero would mean the partition leaks; `leak_warning = False`.

- **attack**: p0=0.496, p1=0.628, p5=0.707, p25=0.856, p50=1.047, p90=2.024; frac below grid = 0.0000
- **benign**: p0=0.286, p1=0.370, p5=0.407, p25=0.462, p50=0.502, p90=0.593; frac below grid = 0.0000

### Per trusted_eval attack family

| family | arm | n | min RMS | median RMS |
|---|---|---|---|---|
| Bot | novel | 1378 | 0.599 | 1.030 |
| DDoS | novel | 1373 | 0.496 | 0.816 |
| PortScan | novel | 1385 | 1.646 | 1.971 |

## trusted_eval family arms (three-way)

- **seen_both** (seed_train ∩ adversary pool): []
- **seed_only** (seed_train only — A4's controlled arm): []
- **novel** (neither — ~0 TPR expected for supervised): ['Bot', 'DDoS', 'PortScan']
