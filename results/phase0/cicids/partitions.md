# Phase 0 partitions

Strategy `within_day_temporal`, config hash `a5883d9b8cb462b3`. Reviewable without re-running; regenerate with `make phase0-explore`.

## Row counts per partition / class

| partition     |   rows |   benign |   attack |   attack_frac | days                                     | classes                                                                                                                                                  |
|:--------------|-------:|---------:|---------:|--------------:|:-----------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------|
| seed_train    | 360257 |   267323 |    92934 |        0.258  | friday,monday,thursday,tuesday,wednesday | BENIGN,Bot,DoS Hulk,DoS Slowhttptest,DoS slowloris,FTP-Patator,PortScan,SSH-Patator,Web Attack - Brute Force,Web Attack - Sql Injection,Web Attack - XSS |
| prod_benign   | 168492 |   168492 |        0 |        0      | friday,monday,thursday,tuesday,wednesday | BENIGN                                                                                                                                                   |
| honeypot_pool | 327595 |   275777 |    51818 |        0.1582 | friday,monday,thursday,tuesday,wednesday | BENIGN,DDoS,DoS GoldenEye,DoS Hulk,Infiltration,PortScan,SSH-Patator                                                                                     |
| trusted_eval  | 190086 |   161465 |    28621 |        0.1506 | friday,monday,thursday,tuesday,wednesday | BENIGN,DDoS,DoS GoldenEye,Heartbleed,Infiltration,SSH-Patator                                                                                            |

## Row counts per partition / day / class

|                                |   attack |   benign |
|:-------------------------------|---------:|---------:|
| ('honeypot_pool', 'friday')    |    36693 |    25649 |
| ('honeypot_pool', 'monday')    |        0 |    72152 |
| ('honeypot_pool', 'thursday')  |       17 |    43865 |
| ('honeypot_pool', 'tuesday')   |      505 |    54864 |
| ('honeypot_pool', 'wednesday') |    14603 |    79247 |
| ('prod_benign', 'friday')      |        0 |    38509 |
| ('prod_benign', 'monday')      |        0 |    49086 |
| ('prod_benign', 'thursday')    |        0 |    28168 |
| ('prod_benign', 'tuesday')     |        0 |    39073 |
| ('prod_benign', 'wednesday')   |        0 |    13656 |
| ('seed_train', 'friday')       |      733 |    58787 |
| ('seed_train', 'monday')       |        0 |    80298 |
| ('seed_train', 'thursday')     |      325 |    40917 |
| ('seed_train', 'tuesday')      |     2239 |    55685 |
| ('seed_train', 'wednesday')    |    89637 |    31636 |
| ('trusted_eval', 'friday')     |    22850 |    17205 |
| ('trusted_eval', 'monday')     |        0 |    41424 |
| ('trusted_eval', 'thursday')   |       16 |    28254 |
| ('trusted_eval', 'tuesday')    |      248 |    32225 |
| ('trusted_eval', 'wednesday')  |     5507 |    42357 |

## Cleaning — rows dropped (CICIDS2017 gotcha list)

| day       |   rows_in |   rows_out_clean |   dropped_nan |   dropped_negative |   dropped_exact_dup |   dropped_bad_ts |   inf_cells_replaced |   near_dups_removed |   imbalance_ratio_out |
|:----------|----------:|-----------------:|--------------:|-------------------:|--------------------:|-----------------:|---------------------:|--------------------:|----------------------:|
| monday    |    529918 |           400398 |           437 |                512 |              128571 |                0 |                  810 |              156905 |                inf    |
| tuesday   |    445909 |           342129 |           264 |                504 |              103012 |                0 |                  327 |              156760 |                 36.69 |
| wednesday |    692703 |           536868 |          1297 |                749 |              153789 |                0 |                 1586 |              259825 |                  1.79 |
| thursday  |    458968 |           314192 |           342 |                616 |              143818 |                0 |                  646 |              172228 |                146.23 |
| friday    |    703245 |           466361 |           527 |                509 |              235848 |                0 |                 1007 |              265561 |                  2.55 |

Drop reasons: whitespace column names, +-Inf in the two rate features (coerced to NaN then dropped), negative Flow Duration artifacts, exact duplicate rows, unparseable timestamps.

## Guard (a) — near-duplicate removal before splitting

Two half-offset grid snaps in normalized feature space (grid `0.02` per-feature RMS), run globally over all days so a cross-day near-duplicate pair is also caught. Removed **1,011,279** of 2,059,948 cleaned rows (49.1%). On synthetic data this clears the injected fingerprint-tight bursts; on real CICIDS2017 it also removes the dataset's heavy benign and DoS self-similarity.

| day | family | rows removed |
|---|---|---|
| friday | BENIGN | 194698 |
| friday | DDoS | 69297 |
| friday | PortScan | 812 |
| friday | Bot | 754 |
| monday | BENIGN | 156905 |
| thursday | BENIGN | 170452 |
| thursday | Web Attack - Brute Force | 1231 |
| thursday | Web Attack - XSS | 542 |
| thursday | Infiltration | 2 |
| thursday | Web Attack - Sql Injection | 1 |
| tuesday | BENIGN | 150683 |
| tuesday | FTP-Patator | 3903 |
| tuesday | SSH-Patator | 2174 |
| wednesday | BENIGN | 176933 |
| wednesday | DoS Hulk | 71564 |
| wednesday | DoS slowloris | 4403 |
| wednesday | DoS Slowhttptest | 4137 |
| wednesday | DoS GoldenEye | 2788 |

## Guard (b) — temporal guard band at internal cuts

Rows within 150s of a cut time dropped so a burst cannot straddle it.

| stream | rows dropped |
|---|---|
| friday/attack | 115 |
| friday/benign | 259 |
| monday/benign | 533 |
| thursday/benign | 402 |
| tuesday/attack | 9 |
| tuesday/benign | 521 |
| wednesday/attack | 87 |
| wednesday/benign | 313 |

## Guard (c) — nearest-neighbour distance, trusted_eval → honeypot_pool

Per-feature RMS distance in normalized space, run for both classes. Concentration near zero would mean the partition leaks; `leak_warning = True`.

- **attack**: p0=0.000, p1=0.000, p5=0.000, p25=0.000, p50=0.006, p90=0.025; frac below grid = 0.8705
- **benign**: p0=0.000, p1=0.000, p5=0.000, p25=0.004, p50=0.009, p90=0.035; frac below grid = 0.7847

### Per trusted_eval attack family

| family | arm | n | min RMS | median RMS |
|---|---|---|---|---|
| DDoS | novel | 22850 | 0.000 | 0.005 |
| DoS GoldenEye | novel | 5500 | 0.000 | 0.021 |
| Heartbleed | novel | 7 | 0.000 | 0.000 |
| Infiltration | novel | 16 | 0.000 | 0.000 |
| SSH-Patator | seen_both | 248 | 0.000 | 0.006 |

## trusted_eval family arms (three-way)

- **seen_both** (seed_train ∩ adversary pool): ['SSH-Patator']
- **seed_only** (seed_train only — A4's controlled arm): []
- **novel** (neither — ~0 TPR expected for supervised): ['Heartbleed']
