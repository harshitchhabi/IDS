# Phase 0 partitions

Strategy `within_day_temporal`, config hash `fdec623c34eb49a3`. Reviewable without re-running; regenerate with `make phase0-explore`.

## Row counts per partition / class

| partition     |   rows |   benign |   attack |   attack_frac | days                                     | classes                                                                                       |
|:--------------|-------:|---------:|---------:|--------------:|:-----------------------------------------|:----------------------------------------------------------------------------------------------|
| seed_train    |  28624 |    20383 |     8241 |        0.2879 | friday,monday,thursday,tuesday,wednesday | BENIGN,DDoS,FTP-Patator,Infiltration,PortScan,SSH-Patator,Web Attack Brute Force              |
| prod_benign   |  13098 |    13098 |        0 |        0      | friday,monday,thursday,tuesday,wednesday | BENIGN                                                                                        |
| honeypot_pool |  27944 |    19951 |     7993 |        0.286  | friday,monday,thursday,tuesday,wednesday | BENIGN,DDoS,DoS Hulk,FTP-Patator,Infiltration,PortScan,Web Attack Brute Force                 |
| trusted_eval  |  17797 |    13262 |     4535 |        0.2548 | friday,monday,thursday,tuesday,wednesday | BENIGN,Bot,DDoS,DoS Hulk,FTP-Patator,Infiltration,PortScan,SSH-Patator,Web Attack Brute Force |

## Row counts per partition / day / class

|                                |   attack |   benign |
|:-------------------------------|---------:|---------:|
| ('honeypot_pool', 'friday')    |     2173 |     3987 |
| ('honeypot_pool', 'monday')    |        0 |     3970 |
| ('honeypot_pool', 'thursday')  |     2293 |     4034 |
| ('honeypot_pool', 'tuesday')   |     1135 |     3987 |
| ('honeypot_pool', 'wednesday') |     2392 |     3973 |
| ('prod_benign', 'friday')      |        0 |     2677 |
| ('prod_benign', 'monday')      |        0 |     2580 |
| ('prod_benign', 'thursday')    |        0 |     2577 |
| ('prod_benign', 'tuesday')     |        0 |     2623 |
| ('prod_benign', 'wednesday')   |        0 |     2641 |
| ('seed_train', 'friday')       |     2373 |     4028 |
| ('seed_train', 'monday')       |        0 |     4040 |
| ('seed_train', 'thursday')     |     2392 |     4111 |
| ('seed_train', 'tuesday')      |     3476 |     4043 |
| ('seed_train', 'wednesday')    |        0 |     4161 |
| ('trusted_eval', 'friday')     |     1666 |     2633 |
| ('trusted_eval', 'monday')     |        0 |     2737 |
| ('trusted_eval', 'thursday')   |     1094 |     2633 |
| ('trusted_eval', 'tuesday')    |     1186 |     2683 |
| ('trusted_eval', 'wednesday')  |      589 |     2576 |

## Cleaning — rows dropped (CICIDS2017 gotcha list)

| day       |   rows_in |   rows_out_clean |   dropped_nan |   dropped_negative |   dropped_exact_dup |   dropped_bad_ts |   inf_cells_replaced |   near_dups_removed |   imbalance_ratio_out |
|:----------|----------:|-----------------:|--------------:|-------------------:|--------------------:|-----------------:|---------------------:|--------------------:|----------------------:|
| monday    |     14210 |            13778 |           195 |                 27 |                 210 |                0 |                  280 |                   0 |                inf    |
| tuesday   |     20706 |            20076 |           290 |                 40 |                 300 |                0 |                  418 |                 185 |                  2.18 |
| wednesday |     17458 |            16927 |           241 |                 33 |                 257 |                0 |                  346 |                  94 |                  4.37 |
| thursday  |     20706 |            20076 |           291 |                 40 |                 299 |                0 |                  418 |                 188 |                  2.19 |
| friday    |     23954 |            23224 |           331 |                 48 |                 351 |                0 |                  476 |                 283 |                  1.45 |

Drop reasons: whitespace column names, +-Inf in the two rate features (coerced to NaN then dropped), negative Flow Duration artifacts, exact duplicate rows, unparseable timestamps.

## Guard (a) — near-duplicate removal before splitting

Two half-offset grid snaps in normalized feature space (grid `0.02` per-feature RMS), run globally over all days so a cross-day near-duplicate pair is also caught. Removed **750** of 94,081 cleaned rows (0.8%). On synthetic data this clears the injected fingerprint-tight bursts; on real CICIDS2017 it also removes the dataset's heavy benign and DoS self-similarity.

| day | family | rows removed |
|---|---|---|
| friday | Bot | 95 |
| friday | DDoS | 94 |
| friday | PortScan | 94 |
| thursday | Web Attack Brute Force | 95 |
| thursday | Infiltration | 93 |
| tuesday | FTP-Patator | 94 |
| tuesday | SSH-Patator | 91 |
| wednesday | DoS Hulk | 94 |

## Guard (b) — temporal guard band at internal cuts

Rows within 150s of a cut time dropped so a burst cannot straddle it.

| stream | rows dropped |
|---|---|
| friday/BENIGN | 439 |
| friday/Bot | 235 |
| friday/DDoS | 219 |
| friday/PortScan | 243 |
| monday/BENIGN | 451 |
| thursday/BENIGN | 424 |
| thursday/Infiltration | 175 |
| thursday/Web Attack Brute Force | 155 |
| tuesday/BENIGN | 430 |
| tuesday/FTP-Patator | 174 |
| tuesday/SSH-Patator | 154 |
| wednesday/BENIGN | 424 |
| wednesday/DoS Hulk | 77 |

## Guard (c) — nearest-neighbour distance, trusted_eval → honeypot_pool

Per-feature RMS distance in normalized space, run for both classes. Only the **attack** class gates `leak_warning` (near-identical benign flows across partitions are normal for real traffic). `leak_warning = False`.

- **attack** (n=4535): p0=0.000, p1=0.395, p5=0.437, p25=0.511, p50=0.571, p90=0.733; frac below grid = 0.0002
- **benign** (n=13262): p0=0.272, p1=0.359, p5=0.390, p25=0.440, p50=0.479, p90=0.564; frac below grid = 0.0000

### Per trusted_eval attack family (NN distance, sampled)

| family | arm | n | min RMS | median RMS |
|---|---|---|---|---|
| Bot | novel | 558 | 0.535 | 0.754 |
| DDoS | seen_both | 557 | 0.349 | 0.550 |
| DoS Hulk | honeypot_only | 589 | 0.364 | 0.536 |
| FTP-Patator | seen_both | 598 | 0.367 | 0.557 |
| Infiltration | seen_both | 537 | 0.000 | 0.567 |
| PortScan | seen_both | 551 | 0.326 | 0.490 |
| SSH-Patator | seed_only | 588 | 0.445 | 0.662 |
| Web Attack Brute Force | seen_both | 557 | 0.359 | 0.545 |

## trusted_eval family arms (four-way)

- **seen_both** (seed_train AND honeypot_pool): ['DDoS', 'FTP-Patator', 'Infiltration', 'PortScan', 'Web Attack Brute Force']
- **seed_only** (seed_train, withheld from pool — A4): ['SSH-Patator']
- **honeypot_only** (pool, not seed_train — decoy-only teaching): ['DoS Hulk']
- **novel** (neither): ['Bot']

### Per-family row counts

Families with <500 trusted_eval rows are excluded from per-family TPR reporting (kept in the data).

| family                 | arm           | arm_source   |   n_seed_train |   n_honeypot_pool |   n_trusted_eval | reportable   |
|:-----------------------|:--------------|:-------------|---------------:|------------------:|-----------------:|:-------------|
| DoS Hulk               | honeypot_only | config       |              0 |              2392 |              589 | True         |
| Bot                    | novel         | config       |              0 |                 0 |              558 | True         |
| SSH-Patator            | seed_only     | config       |           2321 |                 0 |              588 | True         |
| DDoS                   | seen_both     | -            |           1175 |              1103 |              557 | True         |
| FTP-Patator            | seen_both     | -            |           1155 |              1135 |              598 | True         |
| Infiltration           | seen_both     | -            |           1206 |              1140 |              537 | True         |
| PortScan               | seen_both     | -            |           1198 |              1070 |              551 | True         |
| Web Attack Brute Force | seen_both     | -            |           1186 |              1153 |              557 | True         |
