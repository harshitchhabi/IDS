# Phase 0 partitions

Strategy `day_split`, config hash `28d540cd6f0dc47c`. Reviewable without re-running; regenerate with `make phase0-explore`.

## Row counts per partition / class

| partition     |   rows |   benign |   attack |   attack_frac | days           | classes                                                                                  |
|:--------------|-------:|---------:|---------:|--------------:|:---------------|:-----------------------------------------------------------------------------------------|
| seed_train    | 428862 |   425861 |     3001 |        0.007  | monday,tuesday | BENIGN,FTP-Patator,SSH-Patator                                                           |
| prod_benign   | 167209 |   167209 |        0 |        0      | wednesday      | BENIGN                                                                                   |
| honeypot_pool | 141964 |   141606 |      358 |        0.0025 | thursday       | BENIGN,Infiltration,Web Attack - Brute Force,Web Attack - Sql Injection,Web Attack - XSS |
| trusted_eval  | 200800 |   140409 |    60391 |        0.3008 | friday         | BENIGN,Bot,DDoS,PortScan                                                                 |

## Row counts per partition / day / class

|                               |   attack |   benign |
|:------------------------------|---------:|---------:|
| ('honeypot_pool', 'thursday') |      358 |   141606 |
| ('prod_benign', 'wednesday')  |        0 |   167209 |
| ('seed_train', 'monday')      |        0 |   243493 |
| ('seed_train', 'tuesday')     |     3001 |   182368 |
| ('trusted_eval', 'friday')    |    60391 |   140409 |

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

## Guard (c) — nearest-neighbour distance, trusted_eval → honeypot_pool

Per-feature RMS distance in normalized space, run for both classes. Concentration near zero would mean the partition leaks; `leak_warning = True`.

- **attack**: p0=0.000, p1=0.000, p5=0.000, p25=0.000, p50=0.843, p90=0.932; frac below grid = 0.3322
- **benign**: p0=0.000, p1=0.000, p5=0.000, p25=0.008, p50=0.017, p90=0.067; frac below grid = 0.5582

### Per trusted_eval attack family

| family | arm | n | min RMS | median RMS |
|---|---|---|---|---|
| Bot | novel | 399 | 0.000 | 0.491 |
| DDoS | novel | 38861 | 0.000 | 0.844 |
| PortScan | novel | 740 | 0.000 | 0.766 |

## trusted_eval family arms (three-way)

- **seen_both** (seed_train ∩ adversary pool): []
- **seed_only** (seed_train only — A4's controlled arm): []
- **novel** (neither — ~0 TPR expected for supervised): ['Bot', 'DDoS', 'PortScan']
