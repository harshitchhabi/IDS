# Methodology decisions

A running log of the choices that shape what the Phase 0 results *mean*, with
the reasoning behind each. Written for a reviewer: this is the seed of the
paper's methodology section, not a changelog.

---

## 1. Partition strategy: within-day temporal split, not a whole-day split

CLAUDE.md's Phase 0 brief says "split by capture day to avoid temporal
leakage." Splitting whole CICIDS2017 capture days into whole partitions
(`day_split`) does avoid leakage, but it is the wrong experiment, for two
reasons.

**It tests a claim nobody makes.** The honeypot auto-labeling literature claims
a *contemporaneous, within-campaign* benefit: the decoy observes the campaign
that is currently running, the labels are free, and the detector retrained on
them gets better at catching *that* campaign. CICIDS2017 runs each attack family
on its own day, so a whole-day split places every attack family either entirely
inside the honeypot pool or entirely inside the evaluation set, never both. The
S0 checkpoint then measures cross-family generalization — a much harder bar that
the literature never asserts — and S0 could fail for reasons unrelated to
whether the loop is sound.

**It destroys A4 as a variable.** A4 (fingerprint-and-split) is the scenario
where the adversary shows the decoy only a subset of its TTPs. Measuring A4
requires a baseline in which families *are* shown to the decoy, so that
withholding one is a controlled manipulation. Under a whole-day split every
family is already withheld from the honeypot by construction, so there is no
contrast — A4 becomes a partition artifact rather than something the adversary
does.

**Chosen design (`within_day_temporal`, the default).** Split within each
**(day, family) block**, not each day. The first version split each day's benign
and attack *streams* by time — but CICIDS2017 does not interleave its attacks
through a day, it runs them in sequential time blocks (Friday = Bot morning,
PortScan midday, DDoS afternoon), so a per-day 40/40/20 temporal cut routed
whole families to single partitions and re-created the day-split problem at
finer granularity (`seed_only` empty, `seen_both` = one family reported under an
aggregate's name). Grouping by (day, family), sorting each group by timestamp,
and cutting by cumulative fraction fixes this: every family appears in every
partition with temporal ordering intact.

- benign → `seed_train` (0.30) · `prod_benign` (0.20) · `honeypot_pool` (0.30) · `trusted_eval` (0.20)
- attack → `seed_train` (0.40) · `honeypot_pool` (0.40) · `trusted_eval` (0.20)

The eval-family arms are then set explicitly, not left to chance. Two
`PartitionConfig` knobs: `pool_withheld_families` (A4 — a family kept out of
`honeypot_pool`, so it lands in `seed_only`) and `seed_withheld_families` (a
family kept out of `seed_train`, so it lands in `honeypot_only`); a family in
both is `novel`. On CICIDS2017 nothing is withheld by default — S0's baseline is
all-`seen_both` — and A4 experiments set the lists themselves.

**The four eval-family arms** (never folded into an aggregate):

| arm | in seed_train | in honeypot_pool | meaning |
|---|---|---|---|
| `seen_both` | yes | yes | the literature's regime; the loop may improve TPR |
| `seed_only` | yes | no | **A4's controlled measurement arm** |
| `honeypot_only` | no | yes | the loop teaching a family the detector only saw via the decoy — S0's most interesting arm |
| `novel` | no | no | supervised models expected ≈0 |

Per-family TPR is reported with the trusted_eval row count behind every number;
families with <500 trusted_eval rows are excluded from per-family reporting (kept
in the data) because they cannot support a stable rate.

`day_split` is retained as a selectable strategy and reported as a robustness
appendix, not deleted.

## 2. Temporal splits can *false-pass* S0 — three mandatory leakage guards

Most CICIDS2017 attacks are single automated-tool bursts (Hulk, GoldenEye,
PortScan) that emit large numbers of near-identical flow records. Splitting one
such burst by time drops near-duplicate rows into both the honeypot pool and
trusted_eval. A detector retrained on the pool then "improves" on trusted_eval
by memorizing one tool's fingerprint, and the S0 checkpoint passes for the wrong
reason. A false pass here is worse than a false fail: it green-lights the rest
of the project on a foundation that is not real.

Three guards run on every `within_day_temporal` build and are all reported; none
is allowed to pass silently:

- **(a) Hard de-duplication before splitting.** Exact duplicates are removed in
  cleaning. Near-duplicates are removed here, globally over the whole cleaned
  dataset (so a cross-day near-duplicate pair is caught too), with two
  half-offset grid snaps at `near_dup_grid` resolution — the offset pass catches
  a pair that straddled a cell boundary in the first, and both passes are O(n),
  which matters because a single CICIDS DoS burst is hundreds of thousands of
  near-identical rows and a radius neighbour graph over them does not fit in
  memory. The grid resolution is a swept, evidence-justified parameter (§11). A
  guard that never fires is a guard of unknown worth, so the synthetic generator
  injects fingerprint-tight bursts into every attack family and the self-test
  asserts the guard clears them.
- **(b) Temporal guard band.** Rows within `boundary_buffer_seconds / 2` of an
  internal cut time are dropped, so a burst cannot sit across a cut.
- **(c) Nearest-neighbour distance.** For every trusted_eval row, the distance
  in normalized feature space to its nearest honeypot_pool row of the same
  class. Reported as a percentile distribution for *both* classes, but only the
  **attack** class gates `leak_warning`: two different benign HTTP requests have
  identical flow statistics, so near-zero benign NN distance across partitions
  is the normal state of real traffic, not a memorization leak. If the attack
  5th percentile falls below `nn_leak_p5_threshold` (0.25) the build raises
  `leak_warning`, the explore script exits non-zero, and the S0 checkpoint must
  not be trusted until the cause is understood.

## 3. trusted_eval family reporting is four-way — see §1

`seed_only` must never be merged with `novel` into a single "absent" bucket:
only `seed_only` is a controlled manipulation, and collapsing it hides A4's
entire effect. The expectation that the loop helps only `seen_both` is itself a
result we want in the paper — a within-family-only benefit is narrower than the
literature implies, which sharpens the argument that opening an
attacker-controlled write channel is a poor trade.

## 4. The adversary pool is two-class

A1 (benign mimicry) is "point the benign traffic generator at the honeypot."
The adversary pool must therefore contain benign rows for A1 to draw from and
attack rows for S0 and A4, all from the same middle-of-day temporal slice and
disjoint from `seed_train` and `trusted_eval`. An attack-only pool cannot
express A1 at all. Pool volume is sized (~20k rows) so A1 poison ratios up to
50% are reachable with fresh rows rather than resampled duplicates — for tree
models a resampled duplicate is closer to upweighting an existing sample than to
adding new poison, which would understate the attack.

The A1 poison sweep is log-spaced (`0, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5`),
not linear: if A1 does real damage it will show at the low end, and that is
where resolution matters.

## 5. Threshold policy: calibrate to a target FPR, report both modes

No model uses a 0.5 cutoff. Each model's decision threshold is calibrated to a
target operating FPR (default 0.01) on a validation split carved from the
training set (benign-stratified, seeded), and persisted in the model's metadata
sidecar. Calibration is conservative under ties: tree models emit discrete
scores, so the threshold lands on the nearest achievable operating point at or
below the target rather than overshooting it.

Two threshold modes are supported and **both are reported for every run**,
because A1's damage surfaces in different places under each:

- **fixed** — calibrate once at round 0, hold the threshold for all subsequent
  rounds. A1 damage appears as **rising FPR** on trusted benign.
- **recalibrated** — recalibrate each round on trusted benign. FPR stays capped
  by construction; A1 damage appears as **collapsing TPR**.

At Phase 0 with no loop rounds yet, the two modes differ only in that `fixed`
uses the seed-split-calibrated threshold on trusted_eval while `recalibrated`
re-derives the threshold from trusted_eval's own benign rows; `models.csv`
carries both.

## 6. One weight channel — no automatic class rebalancing

No model may use `class_weight="balanced"`, XGBoost's `scale_pos_weight`
auto-heuristics, a weighted or oversampling sampler, SMOTE, or any other
automatic class rebalancing. A1 works by injecting large volumes of
malicious-labeled samples, which shifts the class balance. Any automatic class
weighting would shift in response, and A1's measured effect on the detector
would be entangled with a rebalancing artifact — unattributable. `sample_weight`
is the only channel by which any sample's influence on the fit is adjusted, and
D1 (cost-of-influence weighting) rides entirely on it. For the PyTorch
autoencoder this means `reduction="none"` on the loss, multiplied by the weight
vector, then meaned — never a weighted sampler, whose gradient-variance and
effective-dataset-size semantics differ from true per-sample weights. The rule
is restated in the `dloop.models` package docstring and guarded by a test.

## 7. Retraining semantics: cold-start by default

Each round retrains from scratch. This keeps rounds comparable and prevents
poisoning dynamics from being confounded with optimization path dependence.
Warm-start is a config option; A2 (boundary drift) will likely need it, since
dragging a boundary gradually is more natural with path dependence.

## 8. Scaling and determinism

The feature scaler is fit on the training split only, per round, and persisted
with the model; a test asserts it carries no validation or eval statistics. It
applies `log1p` (every feature is non-negative and heavy-tailed), then
robust-standardizes with the median and `max(IQR, 0.1)`, then clips to ±25. On
real CICIDS2017 many features are near-constant in benign traffic (flag counts
are almost all zero) so their IQR is exactly zero, and dividing the handful of
non-zero rows by a 1e-9 floor exploded them — which is why the autoencoder
scored AUROC 0.59 on the first real-data pass (§10). A flat 0.1-log-unit floor
does not bind on any feature with real spread (synthetic behaviour unchanged)
and the ±25 clip stops a lone extreme value from dominating a reconstruction
loss regardless. Features are stored as float32 through the partition and
leakage guards; CICIDS2017 is ~2.8M rows and flow summary statistics do not need
double precision (the models cast their own float64 copy).

Every `fit` calls a single `seed_everything` that seeds Python, NumPy and
PyTorch and forces deterministic kernels
(`torch.use_deterministic_algorithms(True)`, cuDNN deterministic,
single-threaded); the autoencoder trains full-batch precisely so it is
bit-reproducible. `determinism.md` shows two identical-seed runs producing
identical predictions.

## 9. Python pinned to 3.12

`.python-version` and the `pyproject` constraint pin CPython 3.12. PyTorch wheel
coverage for 3.14 is incomplete and the autoencoder needs torch; pandas 2.3 on
3.14 + NumPy 2.5 also surfaced a `Timedelta` deprecation-to-error. Pinning now
avoids hitting either mid-build.

## 10. Real CICIDS2017 validation — what the synthetic checkpoint hid

The Phase 0 pipeline was run against the real CICIDS2017 `MachineLearningCVE`
CSVs (~2.83M flows, same configs/seeds). Results in `results/phase0/cicids/`,
alongside the synthetic results (`synthetic_vs_cicids.md` is the table). Two
passes: the first surfaced problems, and this section reflects the fixes made in
response.

**Real-data engineering fixes (method unchanged):**

- **Encoding.** Web-Attack labels carry a non-ASCII dash; read with
  `encoding_errors="replace"`, folded to `-` in `normalize_label`.
- **Guard (a) is global and O(n).** A single Wednesday DoS burst is ~230k
  near-identical rows; a radius neighbour graph over that does not fit in
  memory. Guard (a) runs once over the whole cleaned dataset (so cross-day pairs
  are caught) using two half-offset grid snaps — linear, and the offset pass
  catches boundary-straddle pairs a single rounding misses.
- **Memory.** Features stored float32 through the partition; row-content hashing
  and the near-duplicate keys are rolling hashes computed one column at a time;
  the disjointness time-check no longer concatenates all partitions. Needed to
  fit CICIDS2017 in ~2 GB.
- **Guard (c) query subsampled** (pool index stays complete).

**Method changes prompted by the first pass (documented in §1, §2, §8):**

- **Split within each (day, family) block, not each day** (§1). The first pass's
  per-day cut routed whole families to single partitions because CICIDS attacks
  run in sequential daily blocks; `seed_only` was empty and `seen_both` was one
  family under an aggregate's name. After the fix, all 13 real attack families
  land in every partition (`seen_both`); only 3 have ≥500 trusted_eval rows and
  are reportable (DoS Hulk, DDoS, DoS GoldenEye). One tiny family (FTP-Patator,
  5 eval rows, not reportable) lands `seed_only` as a split artifact, flagged
  `arm_source = artifact` in `eval_family_stats.csv`.
- **Only the attack class gates `leak_warning`** (§2). Near-identical benign
  flows across partitions are normal for real traffic, not a leak.
- **Scale floor + clip in the normalizer** (§8): `max(IQR, 0.1)` and a ±25
  clip, to stop near-constant CICIDS features from exploding the autoencoder.

### What the real data showed

1. **CICIDS2017 flow-statistic features are severely degenerate.** Cleaning
   drops 765k rows (27% of raw; 22–34% per day) as exact duplicates. Guard (a)
   removes a further ~1.01M (~49% of cleaned) as near-duplicates at the default
   grid — mostly BENIGN. Real web traffic is highly repetitive in 24
   flow-summary features. §11 sweeps the grid to check this isn't the guard
   doing the attack's job.

2. **`within_day_temporal` still leaks; `day_split` does not.** With the
   attack-class-only gate: `within_day_temporal` raises `leak_warning` (attack
   5th-pct per-feature RMS = **0.003**, ~70% of pairs within grid) — DoS attack
   flows are a near-degenerate cluster and the earliest 40% of a DoS burst is
   near-identical to its latest 20%, so a temporal cut cannot hold out genuine
   test data. `day_split` does **not** raise it (attack p5 = **0.65**): whole
   different days, genuinely different attack families. So on real CICIDS2017,
   `day_split` is the leak-free partition, at the cost of testing cross-family
   generalization rather than the within-campaign claim.

3. **A4's arm cannot occur naturally on CICIDS2017** — every family runs on one
   day. It has to be set with `pool_withheld_families`, and even then only a
   family with enough rows on multiple partitions is measurable; on CICIDS2017
   only the three DoS/DDoS variants qualify. A4 as designed needs synthetic
   augmentation or a second dataset.

4. **`tpr_novel` is family-dependent, not a single number.** Under the leak-free
   `day_split`, RF (fixed) scores Bot **0.08**, PortScan 0.84, DDoS 0.91;
   XGBoost 0.05 / 0.33 / 0.66. Volumetric and scan attacks sit so far outside
   benign that a classifier trained on *any* attacks flags them; a subtle C2
   beacon (Bot) is missed. The synthetic 0.55 was an artifact of every family
   being a shift of one benign profile.

5. **Both threshold modes matter more on real data.** RF `eval_fpr` under
   `fixed` is 0.040 (`within_day`) / 0.053 (`day_split`) vs ~0.01 recalibrated;
   on synthetic the gap is < 0.003.

6. **The autoencoder** scores AUROC ≈ 0.89 on both CICIDS partitions after the
   normalizer fix (§8, §12) — kept — but at 1% FPR its calibrated threshold
   still catches almost nothing (`eval_tpr` 0.06 `within_day`, 0.24 `day_split`).
   RF and XGBoost carry the S0/A1 conclusions.

## 11. Guard (a) grid resolution — swept, not chosen

The near-duplicate guard removes a large fraction of the *benign* class on real
CICIDS2017 at any reasonable grid, and FPR — the paper's headline metric — is
measured against exactly that class. So the grid resolution cannot be a number
picked by feel. `experiments/phase0_grid_sweep.py` runs the partition at
`near_dup_grid` ∈ {off, 0.005, 0.01, 0.02, 0.05} and reports, for each:
rows removed per class, partition sizes, the attack-class leak p5, and RF /
XGBoost trusted_eval FPR / TPR / AUROC (fast estimator configs — this is a
sensitivity check, not the final numbers). Results:
`results/phase0/grid_sweep.csv` (synthetic) and
`results/phase0/cicids/grid_sweep.csv`.

**Synthetic:** completely flat. The guard removes only the ~750 injected
fingerprint rows (0 benign) at every grid; RF trusted_eval TPR stays 0.76–0.77
and AUROC 0.94 across the whole range including *off*.

**CICIDS2017 (`within_day_temporal`):**

| grid | benign removed | attack removed | seed_train rows | RF eval FPR / TPR / AUROC | XGB eval FPR / TPR / AUROC | leak_warning |
|---|---:|---:|---:|---|---|---|
| off | — | — | — | *partition invalid — 12.3k row-content overlaps* | | |
| 0.005 | 574k | 72k | 456k | 0.030 / 0.963 / 0.996 | 0.015 / 0.955 / 0.997 | true |
| 0.01 | 706k | 110k | 409k | 0.034 / 0.969 / 0.991 | 0.028 / 0.965 / 0.996 | true |
| 0.02 | 850k | 162k | 354k | 0.037 / 0.949 / 0.980 | 0.018 / 0.941 / 0.997 | true |
| 0.05 | 1075k | 231k | 267k | 0.021 / 0.952 / 0.988 | 0.014 / 0.954 / 0.996 | true |

Three things this establishes:

1. **The guard is necessary.** With it *off*, `assert_disjoint` fails — CICIDS
   has ~12.3k flows that are content-identical (to 6 dp) across `seed_train` and
   `trusted_eval`. You cannot run without near-duplicate removal on this data.
2. **The results do not hinge on the grid.** From 0.005 to 0.05 the benign rows
   removed range over 2× and `seed_train` shrinks from 456k to 267k, but RF
   AUROC stays 0.98–0.996 and TPR 0.95–0.97; XGB is flatter still. The 49% of
   benign the guard removes at the default looks alarming but the surviving
   distribution supports the same model.
3. **The grid does not fix the leak.** `leak_warning` is set at every grid — the
   `within_day_temporal` DoS-degeneracy leak is a property of the feature
   representation, not a guard artifact.

**Default:** `near_dup_grid = 0.02` — mid-range, and the model metrics are
stable around it. If a future S0/A1 result *does* move materially with this
parameter, that is a red flag (the guard, not the attack, is producing the
effect) and must be surfaced before the result is trusted.

## 12. The autoencoder is kept, with a caveat

The tabular autoencoder scored AUROC 0.59 on the first real-CICIDS pass. The
cause was the normalizer: features that are near-constant in benign CICIDS
traffic (flag counts are almost all zero) have IQR exactly zero, and dividing
their rare non-zero rows by a 1e-9 floor produced values in the millions that
dominated the reconstruction loss. Flooring the scale at `max(IQR, 0.1)` and
clipping the transform to ±25 (§8) raised it to **AUROC ≈ 0.88** on CICIDS while
keeping synthetic AUROC ≈ 0.92 — above the 0.8 keep-bar — so it stays.

The caveat, stated in every results table: at the 1 % target FPR the calibrated
threshold still sits beyond almost every attack (`eval_tpr ≈ 0.003` under
`within_day_temporal`, `≈ 0.15` under `day_split`). The autoencoder *ranks*
attacks above benign but its benign reconstruction-error tail is heavy enough
that a 1 % operating point catches nothing. S0/A1 conclusions are therefore
drawn from RF and XGBoost; the autoencoder is carried as a reference AUROC and
as the anomaly-detector arm the loop will need once its operating point is
worked out (higher target FPR, or a percentile/quantile score rather than raw
reconstruction error).

## 13. Consequence for the S0 checkpoint

After the (day, family) split fix, the four eval-family arms are populated
correctly on synthetic data and S0's per-arm signal is well defined there —
`honeypot_only` (a family the detector sees only through the decoy) is the arm
the loop should move. But the checkpoint still cannot be *validated* on real
data as one partition:

- `within_day_temporal` on CICIDS2017 still raises `leak_warning` (attack NN
  5th-pct = 0.003): real DoS bursts are a degenerate feature-space cluster and
  their early and late flows are near-identical, so no temporal cut holds out
  genuine test data. S0 would pass here by memorization.
- `day_split` on CICIDS2017 is leak-free (attack NN 5th-pct = 0.65) but every
  trusted_eval family is `novel` — it measures cross-family generalization, not
  the within-campaign claim, and has no `honeypot_only` arm at all.

So the loop can be built and exercised on **synthetic data**, where all four
arms exist and no leak fires, with `day_split` CICIDS2017 as a leak-free
real-data cross-check on the `novel` arm. Getting a real-data partition that has
both a populated `honeypot_only` arm *and* no attack-class leak needs either a
less degenerate feature representation (packet-level or sequence features), a
dataset whose campaigns span multiple sessions, or connection-5-tuple-level
disjointness. That is the open question; it does not block building the loop on
synthetic.

## 14. Burst-level splitting — tried, does not fix the leak

> **Erratum (found while building the loop; see §16).** The CICIDS2017 CSVs used
> here (`MachineLearningCVE`) have **no `Timestamp` column**. `clean_flows`
> synthesizes one — 1 row = 1 second, in file order (`synthesized_timestamps`,
> logged as a warning on every run). So on real data every "second" in this
> section, the 2.0 s `burst_gap_seconds`, the 300 s guard band, and the
> "inter-flow gap distribution" in `burst_gap_distribution.csv` are measured on
> that file-order clock: a "gap" is the number of rows of *other* labels between
> two rows of a family, and a "burst" is a run of one family broken by two or more
> other-label rows. That is still a legitimate contiguity split, but it is not a
> time-gap split, and the text below that reads as real inter-arrival time should
> be read as file-order run length. The measured degeneracy does not depend on
> this (§16 shows a uniformly shuffled split gives the same distances); whether a
> split on *real* timestamps changes anything cannot be tested with these files.

§13 left an open question: would replacing the row-level temporal cut with a
burst-aware cut close the gap? A row-level cut through a flood tool's output
seemed like the obvious culprit — Hulk/PortScan/DDoS emit long runs of
near-identical flows, and a fractional-time cut has no way to avoid slicing
through the middle of one. If the leak were really "the cut lands inside a
burst," segmenting each (day, family) stream into contiguous episodes by
inter-flow gap and assigning whole bursts to partitions (never splitting one)
should have raised `nn_attack_p5` well above the 0.25 threshold. It did not.

**Gap distribution first** (`experiments/phase0_burst_gaps.py`, per-family
percentiles of the time between consecutive flows, `results/phase0/cicids/
burst_gap_distribution.csv`). Families split into two groups:

- **Session-like** (Bot, SSH-Patator, FTP-Patator, DoS GoldenEye, Web Attack
  variants): median gap 4-38s, tens to thousands of bursts per day. A row-level
  cut genuinely could slice through one of these.
- **Continuous floods** (DoS Hulk, DDoS, DoS Slowhttptest, PortScan): median gap
  1s or less, gap > 2s for well under 1% of rows. DDoS in particular is ~128k
  rows in **22 bursts** for the whole day — the tool does not pause.

**Implementation** (`PartitionConfig.burst_gap_seconds`, default 2.0s, picked
from the above): `_burst_ids` segments each stream on gaps exceeding the
threshold; `_split_stream_temporal` walks bursts in temporal order and assigns
each one whole to a partition once the running row count crosses the
cumulative split-fraction target, so no burst is ever divided across a
boundary. The old fixed-time guard band is kept as a secondary check on the
*realized* boundary gap, not the primary defense. `tests/test_partition.py`
asserts the invariant directly: reconstructing bursts from the union of all
four partitions, every burst maps to exactly one partition.

**Result, real CICIDS2017, `within_day_temporal`, guard (a) grid 0.005-0.05**
(`results/phase0/cicids/grid_sweep.csv`, burst splitting on):

| grid | nn_attack_p5 | leak_warning |
|---|---:|---|
| 0.005 | 0.0010 | true |
| 0.01 | 0.0016 | true |
| 0.02 | 0.0027 | true |
| 0.05 | 0.0058 | true |

Same order of magnitude as the row-level cut (§11: 0.001-0.0067). Burst
splitting changed essentially nothing. The per-family NN breakdown
(`leakage_report.json` → `nn_by_family`) explains why: DoS Hulk's nearest
`honeypot_pool` neighbour to a `trusted_eval` row has RMS **0.0003**, DDoS
**0.00017**, DoS GoldenEye **0.00017** — a different *burst*, sometimes a
different *day-half*, and the feature vector is still within noise of zero
distance.

**Why**: the working hypothesis in §11/§13 was that the leak is a
*boundary artifact* — a temporal cut severing one continuous burst into two
near-identical halves. The gap-distribution and per-family NN evidence say
otherwise: DoS Hulk, DDoS and DoS GoldenEye are degenerate **for the whole
campaign**, not just within one burst. CICFlowMeter's flow-summary statistics
for a fixed attack tool hitting a fixed target collapse onto a tiny region of
feature space, and that region does not drift meaningfully from the first
burst of the day to the last. Two bursts an hour apart are as
feature-identical as two rows a millisecond apart. Burst-boundary placement was
never the mechanism — no partition boundary, wherever it falls, holds out
information the pool doesn't already have, because there is no temporal
structure in the feature representation to exploit. Session-like families
(SSH-Patator, Bot, Web Attack) do NOT show this degeneracy to the same degree,
consistent with the gap-distribution split above, but they don't carry
`leak_warning` (the attack-class p5 gate) because the flood families dominate
the pooled distribution.

**Conclusion**: this is the negative result CLAUDE.md asked for. Per its
Phase-0 checkpoint instructions, burst splitting was the fix to try before
concluding CICIDS2017 cannot support the within-campaign S0 claim honestly on
`within_day_temporal`; it does not clear the guard, so that conclusion now
stands as settled, not tentative. **CICIDS2017's `within_day_temporal`
partition remains unusable for S0 on the flood-attack families** (DoS Hulk,
DDoS, DoS GoldenEye, PortScan, DoS Slowhttptest) — any measured improvement
there is memorization, not learning, and no amount of guard-(a)/(b) tuning
changes that, because the degeneracy is in the raw feature representation
CICFlowMeter produces for these tools, not an artifact of how the split is
cut. `day_split` remains the only leak-free CICIDS2017 option, at the
already-documented cost of testing cross-family generalization instead. The
loop (part 3 of this request) is built and exercised on **synthetic data**,
where guard (c) passes cleanly and all four eval-family arms are populated;
CICIDS2017's `day_split` `novel`-arm numbers remain a real-data cross-check,
not the primary evidence.

The path to a real-data S0 result — if wanted later — is a different feature
representation (packet/sequence-level, not per-flow summary statistics) or a
dataset whose campaigns are not single continuous tool invocations. Flagging
per CLAUDE.md: this is a methodological limitation worth surfacing before
Phase 3 rather than after.

## 15. The degeneracy is not confined to floods — benign fails guard (c) too, and no family clears the reportable bar

§14 scoped the negative result to "the learning claim on flood families." Two
follow-up measurements narrow it further, in a direction that matters for A1 as
much as S0.

**A1 does not depend on attack-family structure, and it has its own unmeasured
assumption.** A1 poisons `honeypot_pool` *benign* rows and measures FPR on
`trusted_eval` *benign* — `nn_attack_p5` and the flood-family diagnosis in §14
say nothing about it. `phase0_grid_sweep.py` now reports `nn_benign_p5`
alongside `nn_attack_p5` (guard c, benign class, `results/phase0/cicids/
grid_sweep.csv`):

| grid | nn_attack_p5 | nn_benign_p5 |
|---|---:|---:|
| 0.005 | 0.0010 | **0.0007** |
| 0.01 | 0.0014 | 0.0014 |
| 0.02 | 0.0026 | 0.0024 |
| 0.05 | 0.0056 | 0.0058 |

Benign is not cleaner than attack — at every grid it is the same order of
magnitude, at 0.005 slightly *worse*. The expectation that ordinary web/SSH/DNS
browsing is too varied to collapse the way a flood does does not hold on this
dataset: §10 already documented CICIDS2017 benign traffic as "highly repetitive
in 24 flow-summary features" (guard (a) removes ~49% of it as near-duplicate at
the default grid), and guard (c) confirms the repetition survives across the
partition boundary too. Consequence: an A1 FPR increase measured on
`within_day_temporal` cannot yet be told apart from the model rejecting
literal near-copies of specific `trusted_eval` rows it was fed mislabeled,
rather than learning a "benign-shaped-traffic-is-malicious" boundary that
would generalize to production traffic the adversary never touched. That is a
narrower, weaker result than the paper wants to claim, and it applies before
any attack-family reasoning enters — A1 needs its own guard, not a borrowed one.

**No family — attack or, by the same logic, benign — is intrinsically
"structured" once it is actually eligible to teach the loop.** §14's grid
sweep withheld DDoS from `honeypot_pool` (it is the `seed_only`/A4 arm), and
guard (c)'s per-family check searches the *whole* honeypot_pool attack class,
not just same-family rows (module docstring, guard c: "nearest ... row of the
same class" — binary class, not family). Withholding DDoS from the pool
therefore also removed its own near-duplicates from the search, and its
reported `min_rms` (0.0013, just above the 0.001 tier cut) was consequently an
artifact of the withholding, not a property of DDoS traffic. Restoring DDoS to
`seen_both` (own near-duplicates back in the search pool) collapses it to
`min_rms = 3.8e-05` — as degenerate as DoS Hulk.

So the tier measurement has to be taken with every family exposed to
`honeypot_pool` (`seen_both`), which is now how it's computed and committed:
`experiments/phase0_nn_by_family.py --source cicids` (defaults to no
withholding for exactly this reason) → **`results/phase0/cicids/
nn_by_family.csv`**, tier assigned from the measured `min_rms` against a
`DEGENERATE_RMS_THRESHOLD = 0.001` (an order of magnitude below the aggregate
`leak_warning` gate of 0.25, so it is a finer per-family cut, not a restatement
of guard c). At `near_dup_grid = 0.005` (the gentlest grid that still passes
`assert_disjoint`, per the request to stop over-cleaning structured families):

| tier | families | max `n_trusted_eval` among them |
|---|---|---:|
| degenerate | DDoS, DoS GoldenEye, DoS Hulk, DoS Slowhttptest, DoS slowloris, FTP-Patator, PortScan, SSH-Patator, Web Attack - Brute Force, Web Attack - XSS | 30,334 (DoS Hulk) |
| structured | Bot, Heartbleed, Infiltration, Web Attack - Sql Injection | **193** (Bot) |

(`n_trusted_eval` is the true partition count; guard (c)'s own `min_rms` /
`median_rms` are computed on its query-side subsample, capped at 40,000 rows
across the whole trusted_eval attack class — both are in `nn_by_family.csv`.)
Every family with real held-out volume is degenerate; every family that isn't
degenerate has too little volume to report on (Bot's 193 rows is under half
the 500-row bar, and it is the *best* of the four). **No family clears both
bars.** This is the dataset-limit finding CLAUDE.md asked for if burst
splitting and stratification still came up empty: CICIDS2017, under
CICFlowMeter's per-flow summary statistics, does not contain an attack family
that is simultaneously voluminous enough to report on and distinguishable
enough across the partition boundary to demonstrate learning rather than
memorization. Re-pointing `seed_withheld_families` / `pool_withheld_families`
at a "structured" family (as requested) is not possible at current volumes —
there is nothing there to point at.

**Consequence for Phase 0's remaining work.** `pool_withheld_families=("DDoS",)`
/ `seed_withheld_families=("DoS Hulk",)` stay as the A4/`honeypot_only`
configuration in `experiments/_common.py` for real-data volume and
row-count-reporting purposes (`models.csv`'s arm counts are legitimate — n is
n regardless of tier), but neither arm should be read as evidence of learning
on real CICIDS2017: both families are degenerate once exposed to the pool, so
`tpr_seed_only`/`tpr_honeypot_only` there measure memorization capacity, not
generalization. The loop (S0 + A1 + control, per-round metrics, cost
accounting) has **not** been built against real CICIDS2017 pending a decision
on how to proceed, because both of its headline scenarios currently rest on an
unmeasured or now-measured-and-failing assumption on this dataset:

- S0's learning claim has no real-data family that is both reportable and
  non-degenerate (this section).
- A1's FPR claim rests on benign separation that is not clean either (same
  order of magnitude as the attack-class leak).

Options, none exercised yet: (a) build and run S0/A1/control on **synthetic
data only** for Phase 0 (already leak-free on both classes, `nn_benign_p5` not
yet measured there but expected clean given the generator's design — should be
confirmed, not assumed, before leaning on it); (b) find or construct a feature
representation where benign and campaign traffic are not this degenerate
(packet/sequence-level features, or connection-5-tuple-level disjointness, as
§13 already flagged for the attack side); (c) report real-CICIDS2017 S0/A1 as
explicitly measuring worst-case/memorization behavior rather than the
generalization claim, with the degeneracy disclosed up front as this section
does. This is a decision for the next session, not one to make silently by
picking whichever option makes the loop runnable.

## 16. CICIDS2017 degeneracy, measured — and what each dataset can answer

**Claim.** Under CICFlowMeter flow-summary features, CICIDS2017 is low-entropy in
*both* classes: for every attack family with usable volume, and for benign, a
held-out row has a near-identical twin in the training-side pool no matter how
the data is split. It therefore cannot support a *learning* claim for any class
with usable volume. S0's learning claim is not measurable on this dataset — not
"hard", not measurable. (This is the likely reason the literature reports ~99% on
it.) This section is the measurement behind that claim; it replaces the
"blocker" framing of §14–15.

**Table** (`results/phase0/cicids/nn_degeneracy_by_grid.csv`, figure
`degeneracy.png`; burst-level split, every family exposed to `honeypot_pool`,
median per-feature-RMS NN distance from `trusted_eval` to `honeypot_pool` in
normalized space; the guard-(c) "clean" bar is 0.25):

| | n_eval @0.005 | grid 0.005 | 0.01 | 0.02 | 0.05 |
|---|---:|---:|---:|---:|---:|
| BENIGN | 229,695 | 0.0065 | 0.0086 | 0.0108 | 0.0171 |
| DoS Hulk | 30,334 | 0.0055 | 0.0069 | 0.0113 | 0.0161 |
| DDoS | 17,383 | 0.0050 | 0.0063 | 0.0082 | 0.0131 |
| DoS GoldenEye | 1,579 | 0.0130 | 0.0132 | 0.0136 | 0.0177 |
| FTP-Patator | 1,010 | 0.0030 | 0.0036 | 0.0051 | 0.0142 |

Benign 5th percentile: 0.0007 / 0.0014 / 0.0024 / 0.0058 across the four grids.
Every family with >=500 eval rows sits at least 14x below the 0.25 bar at every
grid. Coarser dedup raises the distances only mechanically, by deleting rows
(1.08M rows removed at 0.05), and never approaches the bar. The tier by *minimum*
distance (`nn_by_family.csv`) is grid-sensitive at the margin (DoS GoldenEye flips
to "structured" at 0.05 on a min of 0.002 with a median of 0.018); the **median**
is the robust statistic and is what the figure shows.

**The split is not the cause — a shuffled-partition control.**
`experiments/phase0_degeneracy_control.py` pools each family's rows across
seed_train / honeypot_pool / trusted_eval, shuffles them uniformly, re-splits at
the same sizes, and measures the same statistic against same-family rows only
(`nn_degeneracy_control.csv`). A uniformly random split has no temporal or burst
structure. Median NN, real vs shuffled: BENIGN 0.0067 vs 0.0078, DDoS 0.0049 vs
0.0038, DoS Hulk 0.0054 vs 0.0040, DoS GoldenEye 0.0131 vs 0.0155, FTP-Patator
0.0030 vs 0.0021, SSH-Patator 0.0030 vs 0.0017, Web Attack (XSS, Brute Force) ~0.0014
vs ~0.0014. Real and shuffled agree to within a factor of ~1.5 for benign and
every high-volume family, so no partition of any kind — a split on real
timestamps included, which these files cannot provide (§14 erratum) — can
separate train from eval, because the distances are set by the feature
distribution rather than by where the cut falls.

**What the control also shows.** For the small "structured" families the two
disagree sharply: Bot 1.44 real vs 0.003 shuffled, PortScan 0.44 vs 0.004,
DoS slowloris 1.19 vs 0.003. Under a shuffle they are as degenerate as the rest.
Their apparent separation comes from *session-to-session shift* in file order —
the early and late sessions of one campaign occupy different regions — not from
high per-flow entropy. That is a real, usable kind of held-out-ness (a genuinely
new session), but it exists only for families with <500 eval rows, so it cannot be
reported on. "Structured" in `nn_by_family.csv` should be read as "clustered by
session", not "high entropy".

**Consequence — what each dataset answers.**

| dataset | answers | why |
|---|---|---|
| CICIDS2017 | the degeneracy measurement itself; the A1 damage-vs-distance curve | A1's poison is benign rows stamped malicious; its damage is a function of how far the poison sits from trusted benign, which we can *set* and *measure* on any data. Degeneracy gives the near end of the curve for free (raw benign is the leftmost point). |
| synthetic | S0, A4, all three arms | entropy is controlled by construction (`nn_benign_p5`/`nn_attack_p5` clean, guard (c) passes); S0's learning claim needs held-out signal that real CICIDS does not have. |

Both are real results; synthetic-for-S0 is defensible *because* the measurement
above says why real data cannot carry it.

## 17. The loop, and what A1 actually shows

Built: `dloop.adversary` (`Adversary.generate_batch(round_idx, budget) ->
(DataFrame, CostMetadata)`; `CleanAdversary` = S0, `MimicryAdversary` = A1 with a
jitter knob), `dloop.loop` (`LoopConfig`, auto-labeler, round runner, compact
seeded dataset), `dloop.defense.base` (no-op hook, the real interface; §18).
Runner `experiments/phase0_loop.py` (hard-capped at 4 workers), realized-fidelity
recorder `experiments/phase0_fidelity.py`, report `experiments/phase0_loop_report.py`.
Results: `results/phase0/loop/{cicids,synthetic}/` (per-job CSVs, `config_*.json`
with a config hash, `report.md`, figures, CSVs). Tests: `tests/test_loop.py`.

**Design that matters for reading the numbers.** Control = no ingestion, cold
retrain each round. The model seed varies by round (same across arms) — identical
data + identical seed would make the control bit-identical every round and its
variance exactly zero, so it would not be a noise floor. `sigma_control` = std of
the control metric over seeds x rounds 11-20 (one measurement, so conservative);
"clears control variance" = mean paired final-round delta > 2 sigma_control.
Round 0 is shared by every arm. The x-axis is the **realized** median NN distance
from the injected poison to the full trusted_eval benign set (guard-(c) metric),
not the jitter knob; the full distribution per jitter is in
`mimicry_fidelity_distribution.csv`, and post-jitter poison rows were asserted
disjoint from trusted_eval benign by row content (0 overlaps at every jitter).

**What was run.** 5 seeds, 20 rounds, RF (25 trees, depth <=16) and XGBoost (60
trees), both threshold modes, <=4 workers. RF was cut from a larger config because
one full-size arm cost ~11 min and the grid ~7 h. CICIDS A1 at all seven ratios
{0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5}; jitter {0, 0.01, 0.02, 0.03, 0.05, 0.07,
0.1, 0.2, 0.3, 0.7, 1.5} (realized median 0.011 -> 1.06, roughly log-spaced) at
0.02/0.05/0.1/0.2, and the 6-point subset {0, 0.01, 0.03, 0.1, 0.3, 1.5} at
0.005/0.01/0.5. S0 on CICIDS at all seven ratios (a class-prior *reference*, not a
learning claim). Earlier runs were produced under a superseded `Batch` API; the
refactor to the `generate_batch` API was verified **bit-identical** on four
representative jobs (CICIDS A1, CICIDS control, synthetic S0, synthetic A1: max
abs diff 0.0 over every numeric column), then those runs were reused.

**1. Control noise floor (CICIDS).** Fixed-threshold FPR: RF 0.046, sigma 0.015
(round-to-round 0.013, across seeds 0.007); XGBoost 0.039, sigma 0.010. That is ~4x
the 0.01 target: round-0 calibration uses a validation split carved from a
seed_train full of near-duplicates (§10.5). Recalibrated TPR is noisier (sigma
0.030 RF, 0.020 XGBoost). Synthetic: FPR 0.0085 (sigma 0.0014).

**2-3. A1 on CICIDS: a cliff at copy-level fidelity.** Fixed-threshold FPR
increase over the same-seed control, final round, mean +/- sd over 5 seeds
(2 sigma_control: RF 0.030, XGBoost 0.020; full table in `report.md`):

| ratio | RF, realized 0.011 (raw) | RF, 0.014 | RF, 0.25 | RF, 1.06 | XGB, 0.011 (raw) | XGB, 0.014 | XGB, 0.25 | XGB, 1.06 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.005 | +0.011 | +0.021 | +0.020 | +0.016 | -0.005 | -0.002 | -0.011 | -0.014 |
| 0.01 | +0.032 | +0.007 | +0.019 | +0.012 | -0.000 | -0.006 | -0.009 | -0.008 |
| 0.02 | +0.055 | +0.018 | +0.040 | +0.022 | +0.114 (sd 0.113) | +0.006 | +0.001 | +0.003 |
| 0.05 | **+0.468** | +0.034 | +0.047 | +0.031 | **+0.726** | -0.008 | -0.004 | -0.002 |
| 0.1 | **+0.787** | +0.028 | +0.042 | +0.031 | **+0.902** | +0.003 | -0.004 | +0.003 |
| 0.2 | **+0.921** | +0.042 | +0.052 | +0.037 | **+0.944** | +0.003 | +0.010 | +0.024 |
| 0.5 | **+0.954** | +0.056 | +0.050 | +0.042 | **+0.944** | +0.025 | +0.022 | +0.035 |

Damage falls from catastrophic to the noise floor between realized 0.0111 and
0.0139 — a factor of ~1.3 in distance, **18-25x to the left of the 0.25 mark**.
There is no gradient to read a threshold from: it does not fall off *after* 0.25,
it is already gone by 0.014. The distribution explains the sharpness. Raw poison
has NN percentiles p5 = 0.0009, p25 = 0.0037, median = 0.0102; jitter 0.01 moves
p5 to 0.0079 and p25 to 0.0101. The cliff is the removal of the lower tail of
near-exact twins of trusted_eval benign rows — memorization of near-copies, which
§16 shows exist because CICIDS benign is itself degenerate.

**4. Poison ratio at which A1 first clears control variance** (fixed threshold, FPR;
`a1_first_clears_control_variance.csv`):

- **Raw benign (realized 0.011): RF at 1% (+0.032), XGBoost at 2% (+0.114 but sd
  0.113 — some seeds collapse, some do not). At 5% both are at +0.47/+0.73.** The
  ratio-to-damage relation is sharply nonlinear: 2% -> 5% multiplies RF damage ~9x.
- **Any jitter >= 0.01 (realized >= 0.014): XGBoost never clears below 0.5**, and
  there it is +0.02 to +0.035, below the S0 reference at 0.5 (+0.041). Nothing
  distance-dependent.
- **RF clears at 2-10% for every jitter, but with a flat, distance-independent
  size (+0.02 to +0.056 from 0.014 to 1.06)** — not a mimicry signature. S0 at the
  same ratios raises RF fixed FPR by only -0.003 to +0.029, so class-prior shift
  explains only part of it; A1's excess over S0 is ~+0.02 to +0.04 at ratios <=0.1
  (`first_clears_beyond_s0_ratio`, borderline: S0's own sd is 0.01-0.02). Its
  origin (benign-labeled-malicious noise perturbing a depth-limited forest) is not
  established and it is not claimed as a distance effect.
- **Recalibrated threshold (TPR collapse):** at raw benign both models first clear at
  20% (RF -0.14, XGBoost -0.06); at 50% RF -0.28, XGBoost -0.22. Beyond the cliff
  XGBoost shows no drop; RF drops -0.05 to -0.10 at high ratios far from benign
  (again distance-*increasing*, so again not mimicry).

**A1's damage clears control variance at exactly one place: copy-level fidelity.**
That is not the stop condition (damage does clear), but it bounds the claim: on
CICIDS an attacker who replays benign-like traffic sits there for free, because
the dataset's own benign flows are that repetitive, and 1-2% poison then suffices.
It says nothing about how much a mimic needs against traffic that is not this
degenerate.

**Does the curve travel? Not established.** On synthetic, raw benign sits at
realized NN 0.49 (already right of the cliff), and A1 there does little: RF fixed
FPR +0.001 / +0.011 at 5% / 20%, XGBoost +0.001 / +0.046 (the +0.046 is one seed
spiking, sd 0.084). That is consistent with a cliff near 0.01, but it is one
location inferred from CICIDS plus points on the far side: synthetic cannot reach
the left of the cliff (jitter only adds distance), so where the cliff sits on
other data is untested. A dataset with graded entropy, or a copy-level adversary on
synthetic, would test it.

**5. S0 on synthetic (learning claim, entropy controlled).** Per arm, fixed
threshold, 20% ratio: `honeypot_only` TPR 0.39 (control) -> 0.997 (RF) and 0.34 ->
0.994 (XGBoost), within 1-2 rounds; `seen_both` 0.946 -> 0.961 (RF), 0.950 -> 0.963
(XGBoost), above the control band; `seed_only` flat at ~0.997 (ceiling; A4's arm,
untouched by S0 as intended). Cost: fixed FPR at 50% rises to 0.024 — the same
prior-shift effect. S0 on CICIDS also raises TPR (+0.03 to +0.09) but that is
memorization of degenerate families (§16), not a learning result.

**Not established.** (i) Position of the cliff inside 0.0111-0.0139; (ii) whether the
cliff location is dataset-independent; (iii) the cause of RF's flat sub-cliff
effect; (iv) any defense (D1/D2 not built); (v) `sliding_window` and `fixed_batch`
were implemented and unit-tested but not swept; (vi) RF hyperparameters are the
reduced config above, and only XGBoost jobs were used in the bit-identical
regression (RF runs through identical code).

## 18. Loop configuration: retention and budget mode; why the datasets are split the way they are

The loop's two adversary/defender knobs are **config** (`dloop.loop.config.
LoopConfig`, CLI `--retention/--window/--budget-mode/--batch-size`), not
constants, and each is validated (`sliding_window` needs `window_rounds`;
`window_rounds` without a window is rejected; ratio in [0, 1)).

**Retention.** `accumulate` (default) keeps every admitted honeypot batch for the
rest of the run; `sliding_window` keeps the last `window_rounds` rounds of
batches (seed_train is always kept). Default is `accumulate` because that is the
design the literature proposes ("continuous adaptation") and the worst case for
the defender — influence only ever grows — so it is the setting under which the
paper's claim ("the labeling loop is an attacker-controlled write channel") is
made. The window is the obvious mitigation to test *against* it and is available
for the defense phase; **no sweep in this checkpoint uses it** (unit-tested:
old batches are dropped, cumulative attacker cost is not).

**Budget mode.** `fixed_ratio` sizes the per-round batch so the honeypot share of
the training set reaches `poison_ratio` at the final round (`accumulate`, cumulative
rounding so the final count is exact) or once the window fills (`sliding_window`,
constant per-round budget). Damage curves use it: every point has a known,
comparable poison share. `fixed_batch` gives a constant `batch_size` flows per
round regardless of ratio; the share then *evolves* (linear growth under
`accumulate`, a plateau under a window). Temporal-dynamics experiments use it. All
checkpoint results are `accumulate` + `fixed_ratio`; `fixed_batch` is implemented
and tested but not swept. The recorded `poison_ratio` is retained honeypot rows /
total training rows each round; cumulative attacker cost counts everything the
adversary generated, retained or not (a window forgets data, not effort).

**Adversary API.** `Adversary.generate_batch(round_idx, budget) ->
(pd.DataFrame, CostMetadata)`. `CostMetadata` (flows, packets, bytes, flow-time
seconds) is emitted per batch and passed to the defense hook alongside the batch
and the stamped label, because D1 prices influence by exactly those quantities.
`DefenseHook.apply(batch, cost, stamped_label) -> DefenseDecision(weights, admit)`
is the real interface; the no-op returns weight 1 and admit. D1 supplies weights,
D2 supplies `admit=False`; `sample_weight` remains the only channel, so the round
runner needs no change.

**Realized fidelity, not the knob.** A1's x-axis is the median nearest-neighbour
distance from the injected poison to the full trusted_eval benign set, in the
guard-(c) metric and normalized space. `experiments/phase0_fidelity.py` records
the whole distribution per jitter (p0-p100), not only the median, and asserts by
row content that the *post-jitter* poison rows are disjoint from trusted_eval
benign (the pre-jitter source rows are asserted in the runner). Jitter is roughly
log-spaced in realized distance. Raw benign is the leftmost point and jitter can
only move poison further away, so the sweep cannot go below the dataset's own
duplicate scale: on CICIDS raw poison has p5 = 0.0009, median = 0.0102. (The
"~0.0007" figure quoted for raw benign is a 5th-percentile-type number; the
median, which is what the damage curves use, is 0.0102.)

**Why the datasets are split.** Real CICIDS2017 cannot carry an S0 learning claim
(§16): every family with >=500 eval rows has a median held-out-to-train NN
distance of 0.003-0.013, >=14x below the 0.25 bar at every dedup grid, benign
included (5th percentile 0.0007), and a shuffled split reproduces the same
distances, so no partition can fix it. S0's "improvement" there is memorization
of near-copies. A1, by contrast, does not need held-out attack structure: its
poison is benign rows stamped malicious, its damage is a function of a quantity we
*set and measure* (distance to trusted benign), and degeneracy hands us the
near end of the curve for free. So CICIDS answers the A1 damage-vs-distance curve
and the degeneracy measurement; synthetic — entropy controlled, guard (c) clean —
answers S0 and the three family arms (`seen_both`, `seed_only`, `honeypot_only`;
`novel` is dropped: n=0 with no prospect of filling it). Leading with the
measurement and *then* substituting is what makes synthetic-for-S0 defensible
rather than convenient.
