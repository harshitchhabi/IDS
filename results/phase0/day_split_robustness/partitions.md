# Phase 0 partitions

Strategy `day_split`, config hash `93bd9b3f00ecfd81`. Reviewable without re-running; regenerate with `make phase0-explore`.

## Row counts per partition / class

| partition     |   rows |   benign |   attack |   attack_frac | days           | classes                                    |
|:--------------|-------:|---------:|---------:|--------------:|:---------------|:-------------------------------------------|
| seed_train    |  33669 |    27544 |     6125 |        0.1819 | monday,tuesday | BENIGN,FTP-Patator,SSH-Patator             |
| prod_benign   |  13775 |    13775 |        0 |        0      | wednesday      | BENIGN                                     |
| honeypot_pool |  19888 |    13779 |     6109 |        0.3072 | thursday       | BENIGN,Infiltration,Web Attack Brute Force |
| trusted_eval  |  22941 |    13764 |     9177 |        0.4    | friday         | BENIGN,Bot,DDoS,PortScan                   |

## Row counts per partition / day / class

|                               |   attack |   benign |
|:------------------------------|---------:|---------:|
| ('honeypot_pool', 'thursday') |     6109 |    13779 |
| ('prod_benign', 'wednesday')  |        0 |    13775 |
| ('seed_train', 'monday')      |        0 |    13778 |
| ('seed_train', 'tuesday')     |     6125 |    13766 |
| ('trusted_eval', 'friday')    |     9177 |    13764 |

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

## Guard (c) — nearest-neighbour distance, trusted_eval → honeypot_pool

Per-feature RMS distance in normalized space, run for both classes. Only the **attack** class gates `leak_warning` (near-identical benign flows across partitions are normal for real traffic). `leak_warning = False`.

- **attack** (n=9177): p0=0.452, p1=0.580, p5=0.657, p25=0.807, p50=0.979, p90=1.837; frac below grid = 0.0000
- **benign** (n=13764): p0=0.277, p1=0.361, p5=0.396, p25=0.449, p50=0.488, p90=0.576; frac below grid = 0.0000

### Per trusted_eval attack family (NN distance, sampled)

| family | arm | n | min RMS | median RMS |
|---|---|---|---|---|
| Bot | novel | 3061 | 0.540 | 0.959 |
| DDoS | novel | 3054 | 0.452 | 0.772 |
| PortScan | novel | 3062 | 1.522 | 1.790 |

## trusted_eval family arms (four-way)

- **seen_both** (seed_train AND honeypot_pool): []
- **seed_only** (seed_train, withheld from pool — A4): []
- **honeypot_only** (pool, not seed_train — decoy-only teaching): []
- **novel** (neither): ['Bot', 'DDoS', 'PortScan']

### Per-family row counts

Families with <500 trusted_eval rows are excluded from per-family TPR reporting (kept in the data).

| family   | arm   | arm_source   |   n_seed_train |   n_honeypot_pool |   n_trusted_eval | reportable   |
|:---------|:------|:-------------|---------------:|------------------:|-----------------:|:-------------|
| Bot      | novel | strategy     |              0 |                 0 |             3061 | True         |
| DDoS     | novel | strategy     |              0 |                 0 |             3054 | True         |
| PortScan | novel | strategy     |              0 |                 0 |             3062 | True         |
