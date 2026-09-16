# Phase 0 partitions

Strategy `within_day_temporal`, config hash `c026403465332f72`. Reviewable without re-running; regenerate with `make phase0-explore`.

## Row counts per partition / class

| partition     |   rows |   benign |   attack |   attack_frac | days                                     | classes                                                                                                                                                                                             |
|:--------------|-------:|---------:|---------:|--------------:|:-----------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| seed_train    | 423700 |   344823 |    78877 |        0.1862 | friday,monday,thursday,tuesday,wednesday | BENIGN,Bot,DDoS,DoS GoldenEye,DoS Slowhttptest,DoS slowloris,FTP-Patator,Heartbleed,Infiltration,PortScan,SSH-Patator,Web Attack - Brute Force,Web Attack - Sql Injection,Web Attack - XSS          |
| prod_benign   | 229139 |   229139 |        0 |        0      | friday,monday,thursday,tuesday,wednesday | BENIGN                                                                                                                                                                                              |
| honeypot_pool | 474387 |   344221 |   130166 |        0.2744 | friday,monday,thursday,tuesday,wednesday | BENIGN,Bot,DoS GoldenEye,DoS Hulk,DoS Slowhttptest,DoS slowloris,FTP-Patator,Heartbleed,Infiltration,PortScan,SSH-Patator,Web Attack - Brute Force,Web Attack - Sql Injection,Web Attack - XSS      |
| trusted_eval  | 281749 |   229695 |    52054 |        0.1848 | friday,monday,thursday,tuesday,wednesday | BENIGN,Bot,DDoS,DoS GoldenEye,DoS Hulk,DoS Slowhttptest,DoS slowloris,FTP-Patator,Heartbleed,Infiltration,PortScan,SSH-Patator,Web Attack - Brute Force,Web Attack - Sql Injection,Web Attack - XSS |

## Row counts per partition / day / class

|                                |   attack |   benign |
|:-------------------------------|---------:|---------:|
| ('honeypot_pool', 'friday')    |     1024 |    58174 |
| ('honeypot_pool', 'monday')    |        0 |    91686 |
| ('honeypot_pool', 'thursday')  |      391 |    57514 |
| ('honeypot_pool', 'tuesday')   |     2944 |    70165 |
| ('honeypot_pool', 'wednesday') |   125807 |    66682 |
| ('prod_benign', 'friday')      |        0 |    38767 |
| ('prod_benign', 'monday')      |        0 |    61043 |
| ('prod_benign', 'thursday')    |        0 |    38277 |
| ('prod_benign', 'tuesday')     |        0 |    46674 |
| ('prod_benign', 'wednesday')   |        0 |    44378 |
| ('seed_train', 'friday')       |    71110 |    58294 |
| ('seed_train', 'monday')       |        0 |    91787 |
| ('seed_train', 'thursday')     |      382 |    57636 |
| ('seed_train', 'tuesday')      |     2965 |    70295 |
| ('seed_train', 'wednesday')    |     4420 |    66811 |
| ('trusted_eval', 'friday')     |    17918 |    38852 |
| ('trusted_eval', 'monday')     |        0 |    61125 |
| ('trusted_eval', 'thursday')   |      195 |    38392 |
| ('trusted_eval', 'tuesday')    |     1466 |    46802 |
| ('trusted_eval', 'wednesday')  |    32475 |    44524 |

## Cleaning — rows dropped (CICIDS2017 gotcha list)

| day       |   rows_in |   rows_out_clean |   dropped_nan |   dropped_negative |   dropped_exact_dup |   dropped_bad_ts |   inf_cells_replaced |   near_dups_removed |   imbalance_ratio_out |
|:----------|----------:|-----------------:|--------------:|-------------------:|--------------------:|-----------------:|---------------------:|--------------------:|----------------------:|
| monday    |    529918 |           400398 |           437 |                512 |              128571 |                0 |                  810 |               94090 |                inf    |
| tuesday   |    445909 |           342129 |           264 |                504 |              103012 |                0 |                  327 |              100066 |                 36.69 |
| wednesday |    692703 |           536868 |          1297 |                749 |              153789 |                0 |                 1586 |              150181 |                  1.79 |
| thursday  |    458968 |           314192 |           342 |                616 |              143818 |                0 |                  646 |              120827 |                146.23 |
| friday    |    703245 |           466361 |           527 |                509 |              235848 |                0 |                 1007 |              181035 |                  2.55 |

Drop reasons: whitespace column names, +-Inf in the two rate features (coerced to NaN then dropped), negative Flow Duration artifacts, exact duplicate rows, unparseable timestamps.

## Guard (a) — near-duplicate removal before splitting

Two half-offset grid snaps in normalized feature space (grid `0.005` per-feature RMS), run globally over all days so a cross-day near-duplicate pair is also caught. Removed **646,199** of 2,059,948 cleaned rows (31.4%). On synthetic data this clears the injected fingerprint-tight bursts; on real CICIDS2017 it also removes the dataset's heavy benign and DoS self-similarity.

| day | family | rows removed |
|---|---|---|
| friday | BENIGN | 140467 |
| friday | DDoS | 40033 |
| friday | Bot | 349 |
| friday | PortScan | 186 |
| monday | BENIGN | 94090 |
| thursday | BENIGN | 119700 |
| thursday | Web Attack - Brute Force | 817 |
| thursday | Web Attack - XSS | 309 |
| thursday | Infiltration | 1 |
| tuesday | BENIGN | 98482 |
| tuesday | SSH-Patator | 860 |
| tuesday | FTP-Patator | 724 |
| wednesday | BENIGN | 121119 |
| wednesday | DoS Hulk | 19513 |
| wednesday | DoS slowloris | 3758 |
| wednesday | DoS Slowhttptest | 3436 |
| wednesday | DoS GoldenEye | 2355 |

## Guard (b) — temporal guard band at internal cuts

Rows within 150s of a cut time dropped so a burst cannot straddle it.

| stream | rows dropped |
|---|---|
| friday/BENIGN | 553 |
| friday/Bot | 38 |
| friday/DDoS | 459 |
| friday/PortScan | 137 |
| monday/BENIGN | 667 |
| thursday/BENIGN | 539 |
| thursday/Web Attack - Brute Force | 14 |
| thursday/Web Attack - Sql Injection | 5 |
| thursday/Web Attack - XSS | 20 |
| tuesday/BENIGN | 633 |
| tuesday/FTP-Patator | 103 |
| tuesday/SSH-Patator | 16 |
| wednesday/BENIGN | 628 |
| wednesday/DoS GoldenEye | 36 |
| wednesday/DoS Hulk | 459 |
| wednesday/DoS Slowhttptest | 284 |
| wednesday/DoS slowloris | 183 |

## Guard (c) — nearest-neighbour distance, trusted_eval → honeypot_pool

Per-feature RMS distance in normalized space, run for both classes. Only the **attack** class gates `leak_warning` (near-identical benign flows across partitions are normal for real traffic). `leak_warning = True`.

- **attack** (n=40000): p0=0.000, p1=0.001, p5=0.001, p25=0.003, p50=0.015, p90=0.611; frac below grid = 0.3507
- **benign** (n=40000): p0=0.000, p1=0.000, p5=0.001, p25=0.002, p50=0.007, p90=0.066; frac below grid = 0.4340

### Per trusted_eval attack family (NN distance, sampled)

| family | arm | n | min RMS | median RMS |
|---|---|---|---|---|
| Bot | seen_both | 151 | 0.293 | 0.305 |
| DDoS | seed_only | 13364 | 0.001 | 0.564 |
| DoS GoldenEye | seen_both | 1207 | 0.001 | 0.013 |
| DoS Hulk | honeypot_only | 23314 | 0.000 | 0.004 |
| DoS Slowhttptest | seen_both | 245 | 0.000 | 0.027 |
| DoS slowloris | seen_both | 182 | 0.000 | 0.245 |
| FTP-Patator | seen_both | 771 | 0.000 | 0.003 |
| Heartbleed | seen_both | 1 | 0.510 | 0.510 |
| Infiltration | seen_both | 6 | 0.037 | 0.128 |
| PortScan | seen_both | 253 | 0.001 | 0.128 |
| SSH-Patator | seen_both | 368 | 0.000 | 0.003 |
| Web Attack - Brute Force | seen_both | 86 | 0.000 | 0.001 |
| Web Attack - Sql Injection | seen_both | 2 | 0.003 | 0.022 |
| Web Attack - XSS | seen_both | 50 | 0.000 | 0.001 |

## trusted_eval family arms (four-way)

- **seen_both** (seed_train AND honeypot_pool): ['Bot', 'DoS GoldenEye', 'DoS Slowhttptest', 'DoS slowloris', 'FTP-Patator', 'Heartbleed', 'Infiltration', 'PortScan', 'SSH-Patator', 'Web Attack - Brute Force', 'Web Attack - Sql Injection', 'Web Attack - XSS']
- **seed_only** (seed_train, withheld from pool — A4): ['DDoS']
- **honeypot_only** (pool, not seed_train — decoy-only teaching): ['DoS Hulk']
- **novel** (neither): []

### Per-family row counts

Families with <500 trusted_eval rows are excluded from per-family TPR reporting (kept in the data).

| family                     | arm           | arm_source   |   n_seed_train |   n_honeypot_pool |   n_trusted_eval | reportable   |
|:---------------------------|:--------------|:-------------|---------------:|------------------:|-----------------:|:-------------|
| DoS Hulk                   | honeypot_only | config       |              0 |            121528 |            30334 | True         |
| DDoS                       | seed_only     | config       |          70119 |                 0 |            17383 | True         |
| Bot                        | seen_both     | -            |            392 |               365 |              193 | False        |
| DoS GoldenEye              | seen_both     | -            |           3159 |              3147 |             1579 | True         |
| DoS Slowhttptest           | seen_both     | -            |            619 |               561 |              327 | False        |
| DoS slowloris              | seen_both     | -            |            639 |               568 |              234 | False        |
| FTP-Patator                | seen_both     | -            |           2052 |              2038 |             1010 | True         |
| Heartbleed                 | seen_both     | -            |              3 |                 3 |                1 | False        |
| Infiltration               | seen_both     | -            |             14 |                14 |                6 | False        |
| PortScan                   | seen_both     | -            |            599 |               659 |              342 | False        |
| SSH-Patator                | seen_both     | -            |            913 |               906 |              456 | False        |
| Web Attack - Brute Force   | seen_both     | -            |            237 |               241 |              118 | False        |
| Web Attack - Sql Injection | seen_both     | -            |              7 |                 5 |                3 | False        |
| Web Attack - XSS           | seen_both     | -            |            124 |               131 |               68 | False        |
