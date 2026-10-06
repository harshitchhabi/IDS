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
