# Phase 0 partitions

Strategy `within_day_temporal`, config hash `f1392e544f423199`. Reviewable without re-running; regenerate with `make phase0-explore`.

## Row counts per partition / class

| partition     |   rows |   benign |   attack |   attack_frac | days                                     | classes                                                                                                                                                                                             |
|:--------------|-------:|---------:|---------:|--------------:|:-----------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| seed_train    | 353523 |   267323 |    86200 |        0.2438 | friday,monday,thursday,tuesday,wednesday | BENIGN,Bot,DDoS,DoS GoldenEye,DoS Hulk,DoS Slowhttptest,DoS slowloris,FTP-Patator,Heartbleed,Infiltration,PortScan,SSH-Patator,Web Attack - Brute Force,Web Attack - Sql Injection,Web Attack - XSS |
| prod_benign   | 168491 |   168491 |        0 |        0      | friday,monday,thursday,tuesday,wednesday | BENIGN                                                                                                                                                                                              |
| honeypot_pool | 338373 |   275776 |    62597 |        0.185  | friday,monday,thursday,tuesday,wednesday | BENIGN,Bot,DDoS,DoS GoldenEye,DoS Hulk,DoS Slowhttptest,DoS slowloris,Heartbleed,Infiltration,PortScan,SSH-Patator,Web Attack - Brute Force,Web Attack - Sql Injection,Web Attack - XSS             |
| trusted_eval  | 185572 |   161465 |    24107 |        0.1299 | friday,monday,thursday,tuesday,wednesday | BENIGN,Bot,DDoS,DoS GoldenEye,DoS Hulk,DoS Slowhttptest,DoS slowloris,FTP-Patator,Heartbleed,Infiltration,PortScan,SSH-Patator,Web Attack - Brute Force,Web Attack - Sql Injection,Web Attack - XSS |

## Row counts per partition / day / class

|                                |   attack |   benign |
|:-------------------------------|---------:|---------:|
| ('honeypot_pool', 'friday')    |    22876 |    25649 |
| ('honeypot_pool', 'monday')    |        0 |    72152 |
| ('honeypot_pool', 'thursday')  |       70 |    43864 |
| ('honeypot_pool', 'tuesday')   |      209 |    54864 |
| ('honeypot_pool', 'wednesday') |    39442 |    79247 |
| ('prod_benign', 'friday')      |        0 |    38509 |
| ('prod_benign', 'monday')      |        0 |    49086 |
| ('prod_benign', 'thursday')    |        0 |    28168 |
| ('prod_benign', 'tuesday')     |        0 |    39073 |
| ('prod_benign', 'wednesday')   |        0 |    13655 |
| ('seed_train', 'friday')       |    28945 |    58787 |
| ('seed_train', 'monday')       |        0 |    80298 |
| ('seed_train', 'thursday')     |      237 |    40917 |
| ('seed_train', 'tuesday')      |     2600 |    55685 |
| ('seed_train', 'wednesday')    |    54418 |    31636 |
| ('trusted_eval', 'friday')     |     8280 |    17206 |
| ('trusted_eval', 'monday')     |        0 |    41424 |
| ('trusted_eval', 'thursday')   |       41 |    28253 |
| ('trusted_eval', 'tuesday')    |      190 |    32225 |
| ('trusted_eval', 'wednesday')  |    15596 |    42357 |

## Cleaning — rows dropped (CICIDS2017 gotcha list)

| day       |   rows_in |   rows_out_clean |   dropped_nan |   dropped_negative |   dropped_exact_dup |   dropped_bad_ts |   inf_cells_replaced |   near_dups_removed |   imbalance_ratio_out |
|:----------|----------:|-----------------:|--------------:|-------------------:|--------------------:|-----------------:|---------------------:|--------------------:|----------------------:|
| monday    |    529918 |           400398 |           437 |                512 |              128571 |                0 |                  810 |              156905 |                inf    |
| tuesday   |    445909 |           342129 |           264 |                504 |              103012 |                0 |                  327 |              156760 |                 36.69 |
| wednesday |    692703 |           536868 |          1297 |                749 |              153789 |                0 |                 1586 |              259826 |                  1.79 |
| thursday  |    458968 |           314192 |           342 |                616 |              143818 |                0 |                  646 |              172230 |                146.23 |
| friday    |    703245 |           466361 |           527 |                509 |              235848 |                0 |                 1007 |              265560 |                  2.55 |

Drop reasons: whitespace column names, +-Inf in the two rate features (coerced to NaN then dropped), negative Flow Duration artifacts, exact duplicate rows, unparseable timestamps.

## Guard (a) — near-duplicate removal before splitting

Two half-offset grid snaps in normalized feature space (grid `0.02` per-feature RMS), run globally over all days so a cross-day near-duplicate pair is also caught. Removed **1,011,281** of 2,059,948 cleaned rows (49.1%). On synthetic data this clears the injected fingerprint-tight bursts; on real CICIDS2017 it also removes the dataset's heavy benign and DoS self-similarity.

| day | family | rows removed |
|---|---|---|
| friday | BENIGN | 194697 |
| friday | DDoS | 69297 |
| friday | PortScan | 812 |
| friday | Bot | 754 |
| monday | BENIGN | 156905 |
| thursday | BENIGN | 170454 |
| thursday | Web Attack - Brute Force | 1231 |
| thursday | Web Attack - XSS | 542 |
| thursday | Infiltration | 2 |
| thursday | Web Attack - Sql Injection | 1 |
| tuesday | BENIGN | 150683 |
| tuesday | FTP-Patator | 3903 |
| tuesday | SSH-Patator | 2174 |
| wednesday | BENIGN | 176934 |
| wednesday | DoS Hulk | 71564 |
| wednesday | DoS slowloris | 4403 |
| wednesday | DoS Slowhttptest | 4137 |
| wednesday | DoS GoldenEye | 2788 |

## Guard (b) — temporal guard band at internal cuts

Rows within 150s of a cut time dropped so a burst cannot straddle it.

| stream | rows dropped |
|---|---|
| friday/BENIGN | 259 |
| friday/Bot | 5 |
| friday/DDoS | 285 |
| monday/BENIGN | 533 |
| thursday/BENIGN | 402 |
| thursday/Web Attack - Brute Force | 1 |
| thursday/Web Attack - Sql Injection | 4 |
| thursday/Web Attack - XSS | 5 |
| tuesday/BENIGN | 521 |
| tuesday/SSH-Patator | 2 |
| wednesday/BENIGN | 313 |
| wednesday/DoS GoldenEye | 30 |
| wednesday/DoS Hulk | 196 |
| wednesday/DoS Slowhttptest | 144 |
| wednesday/DoS slowloris | 7 |
| wednesday/Heartbleed | 1 |

## Guard (c) — nearest-neighbour distance, trusted_eval → honeypot_pool

Per-feature RMS distance in normalized space, run for both classes. Only the **attack** class gates `leak_warning` (near-identical benign flows across partitions are normal for real traffic). `leak_warning = True`.

- **attack** (n=24107): p0=0.000, p1=0.002, p5=0.003, p25=0.006, p50=0.012, p90=0.061; frac below grid = 0.7032
- **benign** (n=40000): p0=0.000, p1=0.001, p5=0.002, p25=0.005, p50=0.010, p90=0.039; frac below grid = 0.7579

### Per trusted_eval attack family (NN distance, sampled)

| family | arm | n | min RMS | median RMS |
|---|---|---|---|---|
| Bot | seen_both | 6 | 0.002 | 0.003 |
| DDoS | seen_both | 8075 | 0.000 | 0.008 |
| DoS GoldenEye | seen_both | 3172 | 0.000 | 0.015 |
| DoS Hulk | seen_both | 12002 | 0.000 | 0.014 |
| DoS Slowhttptest | seen_both | 73 | 0.000 | 0.060 |
| DoS slowloris | seen_both | 348 | 0.000 | 0.246 |
| FTP-Patator | seed_only | 5 | 0.182 | 0.425 |
| Heartbleed | seen_both | 1 | 0.511 | 0.511 |
| Infiltration | seen_both | 6 | 0.037 | 0.128 |
| PortScan | seen_both | 199 | 0.001 | 0.013 |
| SSH-Patator | seen_both | 185 | 0.001 | 0.010 |
| Web Attack - Brute Force | seen_both | 16 | 0.001 | 0.013 |
| Web Attack - Sql Injection | seen_both | 4 | 0.003 | 0.040 |
| Web Attack - XSS | seen_both | 15 | 0.004 | 0.028 |

## trusted_eval family arms (four-way)

- **seen_both** (seed_train AND honeypot_pool): ['Bot', 'DDoS', 'DoS GoldenEye', 'DoS Hulk', 'DoS Slowhttptest', 'DoS slowloris', 'Heartbleed', 'Infiltration', 'PortScan', 'SSH-Patator', 'Web Attack - Brute Force', 'Web Attack - Sql Injection', 'Web Attack - XSS']
- **seed_only** (seed_train, withheld from pool — A4): ['FTP-Patator']
- **honeypot_only** (pool, not seed_train — decoy-only teaching): []
- **novel** (neither): []

### Per-family row counts

Families with <500 trusted_eval rows are excluded from per-family TPR reporting (kept in the data).

| family                     | arm       | arm_source   |   n_seed_train |   n_honeypot_pool |   n_trusted_eval | reportable   |
|:---------------------------|:----------|:-------------|---------------:|------------------:|-----------------:|:-------------|
| FTP-Patator                | seed_only | artifact     |           2019 |                 0 |                5 | False        |
| Bot                        | seen_both | -            |            125 |               447 |                6 | False        |
| DDoS                       | seen_both | -            |          28670 |             21667 |             8075 | True         |
| DoS GoldenEye              | seen_both | -            |           1086 |              3200 |             3172 | True         |
| DoS Hulk                   | seen_both | -            |          52520 |             35552 |            12002 | True         |
| DoS Slowhttptest           | seen_both | -            |            484 |               389 |               73 | False        |
| DoS slowloris              | seen_both | -            |            324 |               300 |              348 | False        |
| Heartbleed                 | seen_both | -            |              4 |                 1 |                1 | False        |
| Infiltration               | seen_both | -            |             17 |                10 |                6 | False        |
| PortScan                   | seen_both | -            |            150 |               762 |              199 | False        |
| SSH-Patator                | seen_both | -            |            581 |               209 |              185 | False        |
| Web Attack - Brute Force   | seen_both | -            |            135 |                44 |               16 | False        |
| Web Attack - Sql Injection | seen_both | -            |              8 |                 3 |                4 | False        |
| Web Attack - XSS           | seen_both | -            |             77 |                13 |               15 | False        |
