# Phase 0 partitions

Strategy `within_day_temporal`, config hash `73b51fab903836e0`. Reviewable without re-running; regenerate with `make phase0-explore`.

## Row counts per partition / class

| partition     |   rows |   benign |   attack |   attack_frac | days                                     | classes                                                                           |
|:--------------|-------:|---------:|---------:|--------------:|:-----------------------------------------|:----------------------------------------------------------------------------------|
| seed_train    |  24602 |    20416 |     4186 |        0.1701 | friday,monday,thursday,tuesday,wednesday | BENIGN,DDoS,DoS Hulk,FTP-Patator,PortScan,SSH-Patator,Web Attack Brute Force      |
| prod_benign   |  13104 |    13104 |        0 |        0      | friday,monday,thursday,tuesday,wednesday | BENIGN                                                                            |
| honeypot_pool |  22144 |    19930 |     2214 |        0.1    | friday,monday,thursday,tuesday,wednesday | BENIGN,DDoS,DoS Hulk,PortScan,Web Attack Brute Force                              |
| trusted_eval  |  17593 |    13280 |     4313 |        0.2452 | friday,monday,thursday,tuesday,wednesday | BENIGN,Bot,DDoS,DoS Hulk,Infiltration,PortScan,SSH-Patator,Web Attack Brute Force |

## Row counts per partition / day / class

|                                |   attack |   benign |
|:-------------------------------|---------:|---------:|
| ('honeypot_pool', 'friday')    |     1105 |     3972 |
| ('honeypot_pool', 'monday')    |        0 |     3970 |
| ('honeypot_pool', 'thursday')  |      542 |     4039 |
| ('honeypot_pool', 'tuesday')   |        0 |     3978 |
| ('honeypot_pool', 'wednesday') |      567 |     3971 |
| ('prod_benign', 'friday')      |        0 |     2681 |
| ('prod_benign', 'monday')      |        0 |     2580 |
| ('prod_benign', 'thursday')    |        0 |     2590 |
| ('prod_benign', 'tuesday')     |        0 |     2624 |
| ('prod_benign', 'wednesday')   |        0 |     2629 |
| ('seed_train', 'friday')       |     1095 |     4045 |
| ('seed_train', 'monday')       |        0 |     4040 |
| ('seed_train', 'thursday')     |      521 |     4103 |
| ('seed_train', 'tuesday')      |     2072 |     4053 |
| ('seed_train', 'wednesday')    |      498 |     4175 |
| ('trusted_eval', 'friday')     |     1774 |     2644 |
| ('trusted_eval', 'monday')     |        0 |     2737 |
| ('trusted_eval', 'thursday')   |     1603 |     2637 |
| ('trusted_eval', 'tuesday')    |      690 |     2691 |
| ('trusted_eval', 'wednesday')  |      246 |     2571 |

## Cleaning — rows dropped (CICIDS2017 gotcha list)

| day       |   rows_in |   rows_out_clean |   dropped_nan |   dropped_negative |   dropped_exact_dup |   dropped_bad_ts |   inf_cells_replaced |   near_dups_removed |   imbalance_ratio_out |
|:----------|----------:|-----------------:|--------------:|-------------------:|--------------------:|-----------------:|---------------------:|--------------------:|----------------------:|
| monday    |     14210 |            13778 |           195 |                 27 |                 210 |                0 |                  280 |                   0 |                inf    |
| tuesday   |     17052 |            16533 |           238 |                 34 |                 247 |                0 |                  344 |                   0 |                  4.99 |
| wednesday |     15631 |            15155 |           217 |                 30 |                 229 |                0 |                  312 |                  42 |                  9.97 |
| thursday  |     17052 |            16534 |           238 |                 32 |                 248 |                0 |                  344 |                  41 |                  5.03 |
| friday    |     18473 |            17913 |           255 |                 37 |                 268 |                0 |                  370 |                  82 |                  3.33 |

Drop reasons: whitespace column names, +-Inf in the two rate features (coerced to NaN then dropped), negative Flow Duration artifacts, exact duplicate rows, unparseable timestamps.

## Guard (a) — near-duplicate removal before splitting

Radius-based in normalized feature space (grid `0.02` per-feature RMS). The synthetic generator injects fingerprint-tight bursts into every *sustained* attack family (an automated tool emitting near-byte-identical flows); the guard must clear them or they leak across the temporal cut and let S0 pass by memorization.

| day | family | rows removed |
|---|---|---|
| friday | PortScan | 42 |
| friday | DDoS | 40 |
| thursday | Web Attack Brute Force | 41 |
| wednesday | DoS Hulk | 42 |

## Guard (b) — temporal guard band at internal cuts

Rows within 150s of a cut time dropped so a burst cannot straddle it.

| stream | rows dropped |
|---|---|
| friday/attack | 80 |
| friday/benign | 435 |
| monday/benign | 451 |
| thursday/attack | 35 |
| thursday/benign | 423 |
| tuesday/benign | 425 |
| wednesday/attack | 29 |
| wednesday/benign | 427 |

## Guard (c) — nearest-neighbour distance, trusted_eval → honeypot_pool

Per-feature RMS distance in normalized space, run for both classes. Concentration near zero would mean the partition leaks; `leak_warning = False`.

- **attack**: p0=0.328, p1=0.448, p5=0.522, p25=0.725, p50=0.885, p90=1.332; frac below grid = 0.0000
- **benign**: p0=0.281, p1=0.369, p5=0.401, p25=0.453, p50=0.493, p90=0.580; frac below grid = 0.0000

### Per trusted_eval attack family

| family | arm | n | min RMS | median RMS |
|---|---|---|---|---|
| Bot | novel | 1378 | 0.588 | 0.884 |
| DDoS | seen_both | 133 | 0.363 | 0.607 |
| DoS Hulk | seen_both | 246 | 0.393 | 0.599 |
| Infiltration | novel | 1376 | 0.881 | 1.272 |
| PortScan | seen_both | 263 | 0.328 | 0.527 |
| SSH-Patator | seed_only | 690 | 0.531 | 0.787 |
| Web Attack Brute Force | seen_both | 227 | 0.409 | 0.579 |

## trusted_eval family arms (three-way)

- **seen_both** (seed_train ∩ adversary pool): ['DDoS', 'DoS Hulk', 'PortScan', 'Web Attack Brute Force']
- **seed_only** (seed_train only — A4's controlled arm): ['SSH-Patator']
- **novel** (neither — ~0 TPR expected for supervised): ['Bot', 'Infiltration']
