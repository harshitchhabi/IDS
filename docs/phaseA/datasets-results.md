# Phase A item B — datasets: results

Pre-registration: `docs/DECISIONS.md` §29.B. Session instructions: `docs/phaseA/session-datasets.md`.
Data: `harshitchhabi/IDS-data` at commit `94e9d78`. That commit adds only `NUSW-NB15_features.csv`
and a README edit on top of `af7b05f`; every data zip is byte-identical.

## 0. Which datasets were run

- **Reprocessed CICIDS2017** (`cicids2017-fixed/`, Engelen et al., CNS2022 "improved" release):
  present, run as `--dataset cicids-fixed`.
- **UNSW-NB15** (`unsw-nb15/`): the four headerless part CSVs are present, plus the official column
  dictionary `NUSW-NB15_features.csv`, which was added to IDS-data during this session. Run as
  `--dataset unsw-nb15` after cicids-fixed. Its column mapping is §2, committed before any
  UNSW-NB15 number.

## 1. Column mapping — reprocessed CICIDS2017

*Written and committed before any partition, distance, model or loop number was computed from
this dataset.* Code: `src/dloop/sim/cicids_fixed.py`,
`dloop.features.schema.CICIDS_FIXED_COLUMN_MAP`.

**Features.** All 24 canonical features have a direct analogue (the same CICFlowMeter-derived
statistic as in the original release), so **no canonical feature is dropped** for this dataset.
20 columns keep their original-release names. The four that were renamed in this release map as
follows:

| canonical | original release | reprocessed release |
|---|---|---|
| `fwd_packets` | `Total Fwd Packets` | `Total Fwd Packet` |
| `bwd_packets` | `Total Backward Packets` | `Total Bwd packets` |
| `fwd_bytes` | `Total Length of Fwd Packets` | `Total Length of Fwd Packet` |
| `bwd_bytes` | `Total Length of Bwd Packets` | `Total Length of Bwd Packet` |

The other 20 map exactly as in `CICIDS_COLUMN_MAP`: `Flow Duration`, `Fwd/Bwd Packet Length
Max/Min/Mean`, `Flow Bytes/s`, `Flow Packets/s`, `Flow IAT Mean/Std/Max/Min`, `Fwd IAT Mean`,
`Bwd IAT Mean`, `SYN/PSH/ACK Flag Count`, `Down/Up Ratio`, `Average Packet Size`.

The remaining 67 of the release's 91 columns are not read. These include identifiers (`id`, `Flow
ID`, IPs, ports, `Protocol`), the additional statistics the canonical schema does not use, and the
columns new in this release (`ICMP Code`, `ICMP Type`, `Total TCP Flow Time`,
`Attempted Category`).

**Label and timestamp.** `Label` → `label`, `Timestamp` → `timestamp`. Unlike the original
`MachineLearningCVE` CSVs, this release has real per-flow timestamps (microsecond resolution).
So the within-day temporal split, the burst segmentation (`burst_gap_seconds = 2.0`) and the guard
band (`boundary_buffer_seconds = 300`) run on **real seconds** here, not on the synthesized
1-row-=-1-s file order the original release forces (DECISIONS §14 erratum). The defaults are
unchanged. This is a real difference from CICIDS2017's partition, and it is stated here rather
than tuned around.

**Capture day.** One CSV per day (`monday` … `friday`), tagged from the file name, the same day
names as `cicids.py`.

**"<family> - Attempted" rows are dropped.** Engelen et al. label attack-tool flows that carried no
malicious payload (failed logins, handshakes with no request) as `"<family> - Attempted"`. The
loader excludes them from every partition and logs the dropped count per label and per day.
- **Why not relabel them BENIGN** (Engelen et al.'s own recommendation): that would put
  attack-looking rows labelled benign next to genuine attack rows. That is the same benign/malicious
  label conflict the A1 mechanism measures, so it would contaminate the control arm.
- **Why not keep them as attack families:** that would teach the detector that payload-less
  handshakes are attacks.

**Other labels are kept as the release spells them.** These include `Botnet` (original: `Bot`),
`Portscan` (original: `PortScan`), and `Infiltration - Portscan`, a port scan from the
infiltrated host, which is a genuine attack family and not an "Attempted" label. Any label other
than `BENIGN` is an attack (`is_attack = 1`), as in `clean_flows`.

**Cleaning.** Same pipeline as CICIDS2017 (`dloop.features.cleaning.clean_flows`): Inf→NaN, drop
NaN rows, drop negative rows, drop exact duplicates, all logged.

**Partition.** `within_day_temporal`, same split fractions as CICIDS2017. Family withholding is the
same as CICIDS2017's, so the dataset is the only axis that changes:
- `DDoS` is withheld from `honeypot_pool` (seed_only).
- `DoS Hulk` is withheld from `seed_train` (honeypot_only).

Both families exist in this release under the same names.

**Rules fixed now for the two derived parameters** (each value is recorded below once measured):
- **Near-duplicate grid (guard a).** The same sweep and rule as CICIDS2017 (§11 and `_common.py`):
  run `experiments.phase0_grid_sweep` over grid ∈ {off, 0.005, 0.01, 0.02, 0.05}, take the
  **gentlest grid that passes `assert_disjoint`**, and check that model metrics are insensitive to
  the choice across the sweep.
- **`val-nn-tau`.** The s19 rule: the **smallest tau at which the control arm's fixed-threshold
  FPR is ≤ 1.5× the 0.01 target (≤ 0.015) for both RF and XGBoost**. Measured as the mean over
  rounds 11-20 and 5 seeds, on the tau grid s19 used: {0, 0.005, 0.01, 0.02, 0.05, 0.1}, extended
  upward (0.2, 0.5) only if none of those qualifies.

## 2. Column mapping — UNSW-NB15

*Written and committed before any partition, distance, model or loop number was computed from
this dataset.* Code: `src/dloop/sim/unsw_nb15.py`, `dloop.features.schema.UNSW_COLUMN_MAP` /
`UNSW_FEATURES`.

**Column names.** The four part CSVs (`UNSW-NB15_1..4.csv`, 2,540,047 rows, 49 columns) have no
header row. The loader takes the names, in file order, from the official dictionary
`NUSW-NB15_features.csv` (sorted by its `No.` column). It matches them ignoring case and
whitespace, so the dictionary's `Sload` / `ct_src_ ltm` become `sload` / `ct_src_ltm`. Without
the dictionary the loader refuses to run rather than guess.

**Features: 9 of the 24 canonical features have a direct per-flow analogue.** UNSW-NB15 is
Argus/Bro-derived, not CICFlowMeter-derived. Only the direct analogues are mapped:

| canonical | UNSW-NB15 column (dictionary description) | unit conversion |
|---|---|---|
| `flow_duration` | `dur` (record total duration) | s → µs (×10⁶) |
| `fwd_packets` | `Spkts` (source-to-destination packet count) | — |
| `bwd_packets` | `Dpkts` (destination-to-source packet count) | — |
| `fwd_bytes` | `sbytes` (source-to-destination transaction bytes) | — |
| `bwd_bytes` | `dbytes` (destination-to-source transaction bytes) | — |
| `fwd_pkt_len_mean` | `smeansz` (mean flow packet size transmitted by the src) | — |
| `bwd_pkt_len_mean` | `dmeansz` (mean flow packet size transmitted by the dst) | — |
| `fwd_iat_mean` | `Sintpkt` (source inter-packet arrival time) | ms → µs (×10³) |
| `bwd_iat_mean` | `Dintpkt` (destination inter-packet arrival time) | ms → µs (×10³) |

The unit conversions put durations and inter-arrival times in CICFlowMeter's microseconds. That
keeps the attacker-cost metadata (`adversary/base.py`, which divides duration by 10⁶) in one unit
across datasets. It is a unit change, not a new quantity.

Two analogues are not exact:
- `smeansz` / `dmeansz` are Argus mean *packet* sizes. CICFlowMeter's `Fwd/Bwd Packet Length
  Mean` are mean packet *lengths*. Both are per-direction means of the per-packet size, so they
  are mapped, but the header accounting may differ.
- `Sintpkt` / `Dintpkt` are per-direction mean inter-packet times, the same quantity as
  CICFlowMeter's `Fwd/Bwd IAT Mean`.

**The other 15 canonical features are left out of this dataset's run**, not fabricated:
- `fwd_pkt_len_max`, `fwd_pkt_len_min`, `bwd_pkt_len_max`, `bwd_pkt_len_min`
- `flow_iat_mean`, `flow_iat_std`, `flow_iat_max`, `flow_iat_min`
- `syn_flag_count`, `psh_flag_count`, `ack_flag_count`
- `flow_bytes_per_s`, `flow_pkts_per_s`, `down_up_ratio`, `pkt_size_avg`

The last four could be *derived* from mapped columns (e.g. `(sbytes+dbytes)/dur`). That is not
done, because the derivation would be a choice made here, not a field of the dataset. Likewise
`Sload`/`Dload` (per-direction bits/s) are not `flow_bytes_per_s`. A zero column is not used
either: it would still dilute the per-feature-RMS distance metric. So every UNSW-NB15 distance,
model and loop number is computed on these 9 features.

To support this, the pipeline now carries a per-dataset feature set:
- `schema.check_feature_subset` requires canonical order and that the subset starts with the five
  attacker-cost features.
- The feature set is passed through `clean_flows`, `build_partitions` / `PartitionedData.features`
  and `LoopData.features`.
- The adversary batches are position-based.

The default everywhere is still the full 24-feature canonical set, so the existing datasets'
behaviour is unchanged (full test suite passes).

The remaining 40 UNSW-NB15 columns are not used:
- identifiers and nominals: IPs, ports, `proto`, `state`, `service`
- TTLs, losses, loads, windows and TCP base sequence numbers
- `trans_depth`, `res_bdy_len`, jitter, `Ltime`, TCP setup times
- the `ct_*` / `is_*` connection-window counters

**Labels.** `Label` (0/1) is the binary target and `attack_cat` the family:
- `Label = 0` → `BENIGN`. Otherwise the family is `attack_cat` with whitespace stripped. The
  release has categories with stray spaces, e.g. `" Fuzzers "`.
- `Backdoors` is merged into `Backdoor`: the release spells that family both ways.
- A row whose `Label` and `attack_cat` disagree is dropped and counted, because it can't be
  labelled without guessing which field is wrong. That is `Label = 1` with an empty category, or
  `Label = 0` with a non-empty one.

**Timestamp and capture "day".** `Stime` (record start, unix seconds) → `timestamp`. That is
1-second resolution, real time. UNSW-NB15 was captured in two sessions: 22–23 Jan 2015 (crossing
midnight, Sydney time) and 18 Feb 2015. The day tag is the session (`jan22`, `feb18`, split at
2015-02-01 UTC), not the calendar date, so one session is not cut in two at midnight.

**Cleaning.** The same `clean_flows` pipeline, on the 9 features.

**Partition.** `within_day_temporal`, the same split fractions, burst gap and guard band as the
other datasets (real seconds here, as for cicids-fixed). **No family withholding.** CICIDS2017's
withheld families (DDoS, DoS Hulk) have no UNSW-NB15 counterpart, and choosing new ones would be a
post-hoc choice. So every UNSW-NB15 family is `seen_both`. Withholding only shapes the per-arm
TPR breakdown. It does not change the B.1/B.2 metrics (overall FPR and TPR against the matched
control).

**Derived parameters:** the same two rules as §1, fixed now:
- **Near-duplicate grid:** the gentlest grid in `phase0_grid_sweep`'s sweep that passes
  `assert_disjoint`, with the insensitivity check.
- **`val-nn-tau`:** the s19 rule, the smallest tau with control fixed-FPR ≤ 0.015 for both RF and
  XGBoost (rounds 11-20, 5 seeds).

## 3. Derived parameters and B.0 — reprocessed CICIDS2017

**Loader output.** 2,087,997 rows across 5 days after dropping 11,979 `- Attempted` rows (largest: Botnet 4,067, DoS Slowhttptest 3,368, DoS Slowloris 1,847) (per label,
in `results/phaseA/datasets/cicids-fixed/*.log`, event `loaded reprocessed CICIDS2017 file`).

**Near-duplicate grid (guard a)** (`results/phaseA/datasets/cicids-fixed/grid_sweep.csv`):

| grid | valid | benign removed | attack removed | seed_train | RF eval FPR / TPR / AUROC | XGB eval FPR / TPR / AUROC |
|---|---|---:|---:|---:|---|---|
| off | **no** (8,314 seed_train/trusted_eval row-content overlaps) | | | | | |
| **0.005** | yes | 445,701 | 22,752 | 405,451 | 0.014 / 0.9997 / 0.9994 | 0.015 / 0.989 / 0.998 |
| 0.01 | yes | 562,422 | 46,925 | 360,738 | 0.016 / 0.9994 / 0.9995 | 0.015 / 0.989 / 0.998 |
| 0.02 | yes | 682,351 | 84,649 | 311,095 | 0.016 / 0.999 / 0.9994 | 0.015 / 0.989 / 0.997 |
| 0.05 | yes | 863,132 | 153,248 | 229,980 | 0.013 / 0.994 / 0.9986 | 0.015 / 0.982 / 0.996 |

Rule → **grid = 0.005**, the same value as CICIDS2017's. The insensitivity check passes: RF and
XGBoost AUROC stay within 0.996–0.9995 and TPR within 0.98–1.00 across a 2× range of rows removed.

**`val-nn-tau`** (`tau_sweep/control_floor_by_tau.csv`; control arm, 5 seeds, rounds 11-20,
fixed threshold):

| tau | benign validation rows dropped | RF FPR (sd) | XGB FPR (sd) | RF TPR | XGB TPR |
|---:|---:|---:|---:|---:|---:|
| **0** | 0% | **0.0120** (0.0011) | **0.0145** (0.0028) | 0.986 | 0.956 |
| 0.005 | 9% | 0.0117 (0.0010) | 0.0145 (0.0028) | 0.986 | 0.956 |
| 0.01 | 25% | 0.0096 (0.0009) | 0.0131 (0.0022) | 0.984 | 0.955 |
| 0.02 | 46% | 0.0080 (0.0004) | 0.0113 (0.0028) | 0.981 | 0.954 |
| 0.05 | 73% | 0.0050 (0.0004) | 0.0070 (0.0018) | 0.972 | 0.948 |
| 0.1 | 90% | 0.0017 (0.0011) | 0.0034 (0.0006) | 0.879 | 0.937 |

Rule → **tau = 0**: the calibration filter is off for this dataset. The undefended control's
fixed-threshold FPR is already within 1.5× of the 0.01 target at tau = 0 (RF 0.012, XGBoost
0.0145, the latter close to the 0.015 bar). On CICIDS2017 it was 0.046 / 0.039 (s19). The
round-0 threshold transfers here without the near-twin filter. B.1/B.2 run with
`--val-nn-tau 0`. The fraction of benign validation rows with a training twin is about as high as
on CICIDS2017: 90% within 0.1 RMS here, 94% there. That twin density just does not move the
calibrated threshold as much on this release.

**Limitation found before B.1 ran: DDoS is not in trusted_eval.** With real timestamps, Friday's
DDoS is one continuous burst: 95,144 rows over 19.6 min, largest inter-flow gap 1.76 s, under the
2 s burst gap. Whole-burst assignment (guard b) sends all of it to its first segment
(`seed_train`). So:
- DDoS has no `honeypot_pool` or `trusted_eval` rows.
- The `seed_only` arm, which CICIDS2017's withholding config fills with DDoS, is empty.

The burst gap was fixed in advance (§1) and is not retuned after seeing this. B.1/B.2 use overall
FPR (40,000 benign eval rows) and overall TPR (7,650 attack eval rows across the remaining
families: DoS Hulk 4,000 honeypot_only, plus 3,650 seen_both). Those are defined without DDoS, but
the attack mix differs from CICIDS2017's eval set, which includes DDoS.

**B.0 — degeneracy** (`nn_degeneracy_by_grid.csv`; grid 0.005, every family exposed to
`honeypot_pool`, median per-feature-RMS NN distance `trusted_eval` → `honeypot_pool`, normalized
space; guard-(c) "clean" bar 0.25; families with ≥ 500 eval rows):

| family | n_eval | median NN RMS | min NN RMS | CICIDS2017 median @0.005 (§16) |
|---|---:|---:|---:|---:|
| BENIGN | 201,147 | 0.0107 | 7.0e-05 | 0.0065 |
| DoS Hulk | 23,422 | 0.0077 | 2.7e-05 | 0.0055 |
| DoS GoldenEye | 1,101 | 0.0251 | 0.0016 | 0.0130 |
| Infiltration - Portscan | 904 | 0.0031 | 3.4e-08 | — (not in the original labels) |
| FTP-Patator | 556 | 0.0027 | 2.3e-04 | 0.0030 |
| *all attack* | 27,072 | 0.0079 | 3.4e-08 | — |

Benign 5th percentile: 0.0009. Every family with ≥ 500 eval rows sits at least 10× below the 0.25
bar, as on CICIDS2017. Reprocessing the flows (Engelen et al.) does not remove the degeneracy
§16 measured: it is a property of the CICFlowMeter feature representation of this traffic, not of
the original release's extraction bugs. Benign and DoS GoldenEye are about 1.5–2× farther than in
the original. `leak_warning` is set, as on CICIDS2017.

## 4. Derived parameters and B.0 — UNSW-NB15

**Loader output.** 2,540,047 rows: 1,087,203 in session `jan22`, 1,452,844 in `feb18`. 0 rows had a
disagreeing `Label` / `attack_cat`. Families: BENIGN 2,218,764, Generic 215,481, Exploits 44,525,
Fuzzers 24,246, DoS 16,353, Reconnaissance 13,987, Analysis 2,677, Backdoor 2,329 (after merging
`Backdoors`), Shellcode 1,511, Worms 174. Cleaning drops 837,115 rows, all exact duplicates on the
9 features (no NaN/Inf or negative rows), leaving 1,702,932.

**Near-duplicate grid (guard a)** (`results/phaseA/datasets/unsw-nb15/grid_sweep.csv`):

| grid | valid | benign removed | attack removed | seed_train | RF eval FPR / TPR / AUROC | XGB eval FPR / TPR / AUROC |
|---|---|---:|---:|---:|---|---|
| off | **no** (994 seed_train/trusted_eval row-content overlaps) | | | | | |
| **0.005** | yes | 1,268,104 | 5,089 | 145,800 | 0.014 / 0.744 / 0.988 | 0.012 / 0.643 / 0.988 |
| 0.01 | yes | 1,434,755 | 8,663 | 82,138 | 0.018 / 0.642 / 0.980 | 0.010 / 0.564 / 0.980 |
| 0.02 | yes | 1,531,727 | 15,543 | 50,551 | 0.029 / 0.621 / 0.968 | 0.012 / 0.494 / 0.968 |
| 0.05 | yes | 1,602,470 | 31,524 | 23,083 | 0.027 / 0.517 / 0.957 | 0.023 / 0.463 / 0.953 |

Rule → **grid = 0.005**. **The insensitivity check does not pass cleanly here, unlike CICIDS2017
and cicids-fixed.** From 0.005 to 0.05:
- RF TPR falls from 0.74 to 0.52 and AUROC from 0.988 to 0.957. XGBoost follows the same pattern.
- Even the gentlest valid grid removes 1.27M benign rows: on 9 features, most benign UNSW-NB15
  flows have a near-twin.

The grid was chosen by the pre-fixed rule (gentlest valid), not by these metrics. Read UNSW-NB15
results as conditional on grid 0.005. A coarser guard would have produced a smaller, harder
dataset.

**`val-nn-tau`** (`tau_sweep/control_floor_by_tau.csv`; control arm, 5 seeds, rounds 11-20,
fixed threshold):

| tau | benign validation rows dropped | RF FPR (sd) | XGB FPR (sd) | RF TPR | XGB TPR |
|---:|---:|---:|---:|---:|---:|
| **0** | 0% | **0.0120** (0.0010) | **0.0107** (0.0008) | 0.630 | 0.620 |
| 0.005 | 55% | 0.0062 (0.0011) | 0.0042 (0.0013) | 0.488 | 0.485 |
| 0.01 | 79% | 0.0035 (0.0016) | 0.0014 (0.0004) | 0.396 | 0.385 |
| 0.02 | 92% | 0.0016 (0.0008) | 0.0004 (0.0002) | 0.311 | 0.266 |
| 0.05 | 97% | 0.0001 (0.0002) | 0.0002 (0.0002) | 0.135 | 0.171 |
| 0.1 | (fallback) | 0.0120 | 0.0107 | 0.630 | 0.620 |

Rule → **tau = 0**, calibration filter off; B.1/B.2 run with `--val-nn-tau 0`. At tau = 0.1 fewer
than 100 twin-free benign validation rows remain. The existing fallback in
`Model._calibration_mask` then calibrates on all rows, so that row reproduces tau = 0 exactly. It
is not a measurement at 0.1.

The undefended detector is much weaker here than on either CICIDS2017 release: TPR ≈ 0.63 at ≈ 1%
FPR, AUROC 0.987 (`seed_train` subsample, 9 features). B.1 measures A1's damage against that
baseline.

**B.0 — degeneracy** (`nn_degeneracy_by_grid.csv`; grid 0.005, no withholding, median
per-feature-RMS NN distance `trusted_eval` → `honeypot_pool`, normalized 9-feature space;
families with ≥ 500 eval rows):

| family | n_eval | median NN RMS | min NN RMS |
|---|---:|---:|---:|
| BENIGN | 66,950 | 0.0037 | 1.9e-04 |
| Exploits | 4,966 | 0.0134 | 0 |
| Fuzzers | 3,126 | 0.0067 | 0 |
| DoS | 782 | 0.0140 | 0 |
| Generic | 748 | 0.0172 | 0 |
| Reconnaissance | 737 | 0.0053 | 0 |
| *all attack* | 10,859 | 0.0100 | 0 |

Benign 5th percentile: 0.0013. Every family with ≥ 500 eval rows is 14× or more below the 0.25
bar, so UNSW-NB15 on this mapping is as degenerate as CICIDS2017. Benign (0.0037) is closer than
on either CICIDS release.

A minimum of exactly 0 for attack families is genuine, not a partition leak. The guard-(c) search
for an attack family runs against *all* attack rows in `honeypot_pool`. On 9 features, identical
vectors recur under *different* UNSW-NB15 attack categories, e.g. an Exploits row identical to a
DoS row. The partition's row hash includes the label, so those are allowed across partitions
(`assert_disjoint` passes). They are the 9-feature representation's own label ambiguity. Only 748
of Generic's 215,481 rows survive to trusted_eval: Generic is massively duplicated on these
features.
