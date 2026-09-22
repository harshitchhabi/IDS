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

> **Superseded in part by §19.** Every fixed-threshold FPR number in this section used the old
> round-0 calibration, which put the control at FPR 0.046 against a 0.01 target. With an honest
> baseline the poison ratio needed drops out of the 1-2% range (first clears at ~10%, catastrophic
> from ~20%), and the flat RF effect beyond the cliff disappears (§19.1). The cliff, the
> distribution analysis and the recalibrated-threshold TPR results stand.

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

## 19. Calibration baseline fixed; the two A1 mechanisms separated; timestamp check

### 19.1 The round-0 threshold did not transfer — and fixing it changes the headline

**Problem.** The control's fixed-threshold FPR was 0.046 (RF) / 0.039 (XGBoost) against a
0.01 target. The round-0 threshold is calibrated on a validation split carved from
seed_train, which on this data is full of near-copies of training rows, so calibration FPR
is optimistic and the threshold too low.

**Fix.** `ModelConfig.val_min_nn_distance` (`LoopConfig.val_min_nn_distance`): calibrate
only on validation rows with no same-class training row within `tau` (per-feature RMS,
normalized space, the guard-(c) metric). Off (0) is bit-identical to before (verified on four
jobs, and the config hash is unchanged when off). This is the exact-distance form of "apply
the near-dup grid to validation before calibration": the partition's guard (a) at grid 0.005
already removes same-cell duplicates, so a grid-cell dedup of the validation split is a
no-op at that resolution; the residual twins sit at 0.005-0.1 RMS.

**Choosing tau (rule stated first: the smallest tau at which control fixed-FPR <= 1.5x the
target).** Control arm, 5 seeds, rounds 11-20 (`cicids_recal/control_floor_by_tau.csv`):

| tau | validation benign rows dropped | RF FPR (sigma) | XGB FPR (sigma) | RF TPR | XGB TPR |
|---:|---:|---:|---:|---:|---:|
| 0 (old) | 0% | 0.046 (0.015) | 0.039 (0.010) | 0.876 | 0.869 |
| 0.005 | 10% | 0.051 (0.014) | 0.052 (0.013) | 0.878 | 0.877 |
| 0.01 | 22% | 0.047 (0.014) | 0.049 (0.012) | 0.876 | 0.875 |
| 0.02 | 42% | 0.041 (0.015) | 0.047 (0.014) | 0.874 | 0.875 |
| 0.05 | 74% | 0.025 (0.011) | 0.031 (0.011) | 0.863 | 0.863 |
| **0.1** | **94%** | **0.007 (0.005)** | **0.006 (0.006)** | 0.806 | 0.798 |

`tau = 0.1` is the new baseline. AUROC is identical at every tau (the model does not
change; only the threshold does). The shift is itself evidence for §16: **94% of benign
validation rows have a training twin within 0.1 RMS** (42% within 0.02), and the operating
point only becomes honest once they are discarded. The price is a coarse calibration set
(~300 benign rows) and TPR falling by ~0.07-0.08. The recalibrated-threshold mode never uses
the round-0 threshold, and its results are identical under both calibrations to every digit
(a sanity check that only the fixed threshold changed).

**Effect on A1 (raw benign fidelity, jitter 0; fixed-threshold FPR rise over control, mean
+/- sd over 5 seeds; 2 sigma_control old -> new: RF 0.030 -> 0.009, XGBoost 0.020 -> 0.012):**

| ratio | RF old | RF new | XGB old | XGB new |
|---:|---:|---:|---:|---:|
| 0.005 | +0.011 +/- 0.006 | -0.002 +/- 0.003 | -0.005 +/- 0.007 | +0.001 +/- 0.002 |
| 0.01 | +0.032 +/- 0.027 | -0.002 +/- 0.005 | -0.000 +/- 0.015 | -0.002 +/- 0.005 |
| 0.02 | +0.055 +/- 0.023 | +0.003 +/- 0.004 | +0.114 +/- 0.113 | -0.002 +/- 0.006 |
| 0.05 | **+0.468** +/- 0.049 | +0.009 +/- 0.006 | **+0.726** +/- 0.039 | +0.005 +/- 0.007 |
| 0.1 | +0.787 +/- 0.025 | +0.025 +/- 0.005 | +0.902 +/- 0.028 | +0.014 +/- 0.023 |
| 0.2 | +0.921 +/- 0.010 | **+0.337** +/- 0.139 | +0.944 +/- 0.018 | **+0.279** +/- 0.374 |
| 0.5 | +0.954 +/- 0.011 | **+0.880** +/- 0.024 | +0.944 +/- 0.019 | **+0.563** +/- 0.457 |

- The poison ratio at which A1 first clears control variance moves from **1% (RF) / 2%
  (XGBoost) to 10%** (RF +0.025, XGBoost +0.014, both marginal), with catastrophic damage
  from **20%**. §17's "1-2% poison suffices" was an artifact of the miscalibrated baseline:
  a threshold set too low is hypersensitive to small score shifts. The damage is still
  real, and still a cliff, but it needs 5-10x more poison than §17 said.
- At 20% and 50% the seed spread is enormous (XGBoost sd 0.37-0.46): the outcome is
  bimodal across seeds (some retrains collapse, some do not), so a single-seed run would
  be misleading either way.
- **Just past the cliff (jitter 0.01, realized NN 0.014) the flat RF effect §17 reported
  (+0.03-0.05) disappears:** new-calibration RF +0.001 / +0.004 at 5% / 20%, XGBoost -0.002 /
  -0.003. It was also a calibration artifact.
- The cliff itself (§17, the distribution of near-exact twins) is unaffected: damage exists
  only at copy-level fidelity.

### 19.2 Two mechanisms, separated

Test (`experiments/phase0_mechanism_report.py`): inject the same number of rows at the same
realized distance (jitter 0.7, realized NN ~0.56, well right of the cliff), varying one thing
at a time — **a1** benign+jitter stamped malicious; **a1truth** the same rows stamped with their
true label; **s0j** genuine attack rows + the same jitter, stamped malicious (same class-prior
shift and jitter texture, no benign-label conflict); **s0** genuine attack rows, no jitter.
Same-seed paired deltas vs control, final round, 5 seeds (`results/phase0/mechanism/`).

Fixed-threshold FPR rise, ratios 0.05 / 0.2:

| | RF old cal | RF new cal | XGB old cal | XGB new cal |
|---|---:|---:|---:|---:|
| a1 (label conflict) | +0.038 / +0.054 | +0.004 / +0.011 | +0.003 / +0.021 | -0.003 / -0.003 |
| s0j (prior shift + jitter) | +0.013 / +0.021 | +0.001 / +0.004 | -0.003 / +0.020 | -0.004 / -0.005 |
| s0 (prior shift) | +0.009 / +0.026 | +0.002 / +0.002 | +0.028 / +0.029 | -0.002 / -0.002 |
| a1truth (same rows, true label) | -0.010 / -0.016 | -0.005 / -0.005 | -0.018 / -0.014 | -0.004 / -0.005 |
| a1 - s0j | +0.025 / +0.033 | +0.003 / +0.007 | +0.006 / +0.001 | +0.001 / +0.002 |
| 2 sigma_control | 0.030 | 0.009 | 0.020 | 0.012 |

Recalibrated-threshold TPR change (identical under both calibrations), ratios 0.05 / 0.2:

| | RF | XGBoost |
|---|---:|---:|
| a1 | **-0.085 / -0.109** | +0.023 / +0.017 |
| s0j | -0.003 / -0.002 | +0.054 / +0.049 |
| a1truth | +0.015 / +0.014 | -0.041 / -0.097 |
| s0 | +0.058 / +0.079 | +0.053 / +0.084 |
| 2 sigma_control | 0.061 | 0.040 |

> **Erratum (§22).** The verdict below was too strong for the *FPR* half. It rested on `s0`/`s0j`, which
> place their rows in attack regions. A `junk` arm (bulk rows resembling neither class) reproduces the
> old-calibration flat FPR effect at A1's size, so that effect is volume-driven ("prior shift"); it is
> gated by calibration and vanishes under the honest threshold (§22.1). The verdict stands for the RF
> recalibrated-TPR channel, which `junk` does not reproduce (§22.2).

**Verdict on the hypothesis "the flat effect is class-prior shift".** Not supported as
stated.

- Class-prior shift alone (s0, s0j: same row count, malicious label, no benign conflict)
  reproduces only a fraction of the old-calibration RF FPR effect (+0.009..+0.026 against
  +0.038/+0.054), and **none** of it under the honest calibration (+0.001..+0.004, inside
  2 sigma). XGBoost shows a small prior-shift effect only under the old, too-low threshold
  (+0.028 / +0.029).
- The same rows stamped with their true label (a1truth) do not raise FPR (all <= 0). So the
  jitter texture and the extra benign data are not the cause; the label is.
- What remains is the label conflict acting at distance, and it is **small and RF-specific**:
  FPR <= +0.011 (a1 - a1truth <= +0.016) under the honest calibration, at the edge of noise,
  and a TPR drop of **0.09-0.11 for RF under the recalibrated threshold** where s0j and
  a1truth show none (a1 - s0j = -0.083 / -0.107; XGBoost shows no drop). Mechanism: benign-like
  rows stamped malicious lift scores across benign neighbourhoods slightly; a recalibrated
  threshold rises to hold FPR at 1%, and TPR pays for it.

So the two named mechanisms, with sizes under the honest calibration:

| mechanism | needs | size | where it shows |
|---|---|---|---|
| **label conflict at copy fidelity** | near-exact reproduction of trusted benign rows (realized NN <~ 0.014) and >= 10-20% poison | catastrophic: FPR +0.34 to +0.88 (RF), bimodal for XGBoost | fixed threshold (FPR); also TPR collapse under recalibration (§17) |
| **label conflict at a distance** (plus class-prior shift, which is ~0 here) | no fidelity | small; RF only: TPR -0.09..-0.11 (recalibrated), FPR <= +0.016 | recalibrated threshold (TPR); FPR only under a mis-set low threshold |

The clean "prior shift" story (any distance, small, no fidelity) does not survive: prior
shift is negligible once the baseline is honest.

### 19.3 Timestamp check (no re-run, as instructed)

Available, but not obtained. The timestamped release, `GeneratedLabelledFlows.zip` (the
`TrafficLabelling` CSVs with `Timestamp`, Flow ID and IPs), is listed as "publicly available
for researchers" on the UNB CIC page
(https://www.unb.ca/cic/datasets/ids-2017.html). The download host it links
(http://cicresearch.ca/CICDataset/CIC-IDS-2017/) currently gates the files behind a form asking
for personal details, and returned a server error when checked, so nothing was downloaded
(submitting personal details is for the user to do, not something to do on their behalf). A
Hugging Face mirror's README does not state which variant or columns it carries, so it was not
trusted. **Two caveats to verify on obtaining it, from memory and not confirmed here:** its
`Timestamp` is reportedly in a 12-hour format without AM/PM (afternoon rows are ambiguous),
and the release has documented flow-construction and labeling issues in the literature.
Until then the §14 erratum and the shuffled-partition control (§16) stand as the honest
answer.

## 20. D1 — cost-of-influence weighting: the definition, fixed before any D1 result

Written and committed to the log **before** `d1_cost_weighting.py` was implemented and
before any defended run, so the parameters below are not tuned to the outcome.

**Idea.** A honeypot sample's influence on the retrained model is its
`sample_weight` (the single weight channel). D1 makes that influence *purchasable
with attacker effort*: `w_i = W(cost_i)`, with `W` monotone and `W(0) = 0`. Cheap
interactions get near-zero weight; only interactions that cost the attacker real
effort get full weight. Poisoning is attractive only while it is cheap; D1 removes
that.

**Cost record (per flow).** `CostMetadata.per_flow`, the same record the batch
totals are summed from: `x_i = (d_i, p_i, b_i, s_i)` = duration (seconds), packets
(fwd + bwd), bytes (fwd + bwd), and protocol-state depth `s_i = min(fwd_packets,
bwd_packets)`, the number of request/response exchanges the flow sustained. Depth is
the flow-level stand-in for what a Phase 3 honeypot log would report as commands
executed / protocol state reached / files transferred; nothing in D1 depends on the
stand-in beyond "a per-sample non-negative effort vector".

**Reference scale.** `r_k` = median of component `k` over the **benign rows of
seed_train** (defender-owned, trusted, no eval data): one unit is "what a typical
legitimate flow costs". A floor of 1e-9 guards a zero median.

**Effort.**
`e_i = prod_k (1 + x_ik / r_k)^alpha_k - 1`, `alpha_k = 1/4` (geometric mean).
Properties: `e_i = 0` iff every component is 0; strictly increasing in every
component; dimensionless and invariant to the units of each component (each is
divided by its own reference); `e_i = 1` for a flow that costs a median benign flow's
worth in every component.

**Weight.** `w_i = min(1, (e_i / E*)^gamma)`. `E*` is the saturation effort in units
of a typical benign flow; `gamma >= 1` sets how sharply weight grows below it.
Properties (each unit-tested): `w in [0, 1]`; `w(0) = 0`; non-decreasing in every
component; per-flow costs sum to the `CostMetadata` totals.

**Pre-registered default: `E* = 8`, `gamma = 2`.** A median benign flow weighs
`(1/8)^2 = 0.016`; full influence needs roughly an order of magnitude more effort
than a typical legitimate flow. Chosen by that design principle, not by sweeping.

**Effective poison mass.** `M_eff = sum_i w_i`. An attacker copying benign flows
(`e ~ 1`) needs `N ~ M / w_bar` flows to buy mass `M`, i.e. cost scales with
`1 / w_bar`. Raising the weight by padding the flow (more duration/packets/bytes)
is possible, but the cost features are also model features, so padding moves the
row *away* from the benign rows it copies; §17 showed A1's damage lives only at
copy-level fidelity (realized NN <~0.014). The claim under test is that copy-level
fidelity and high weight are in tension. It is tested directly with a padding
adversary (`cost_padding = m` scales duration, packets and bytes) rather than
asserted.

**Known cost, stated in advance.** Genuine attacks that are themselves cheap
per flow (floods, scans: one tiny flow each) also get low weight, so D1 will reduce
what S0 can teach the detector about them. This utility cost is measured (S0 on
synthetic, per arm) and reported next to the A1 recovery, not left out.

**Sensitivity protocol (pre-registered).** (a) `E* in {2, 4, 8, 16, 32}` x `gamma in
{1, 2, 3}`, XGBoost, CICIDS A1 at raw benign (jitter 0), ratios 0.05 and 0.2, 5
seeds. (b) Component ablation at the default `(E*, gamma)`: duration-only,
packets-only, bytes-only, depth-only. **"Not sensitive" is defined as: A1 FPR damage
stays within 2 sigma_control over the whole region `E* >= 4, gamma >= 1`.** If it does
not, the region where it fails is reported instead.

**Generic baselines (fixed hyperparameters, not tuned on A1).**

- *Loss-based filtering.* At each retrain, an auxiliary XGBoost (40 trees, depth 4)
  produces 3-fold out-of-fold probabilities over the training set; honeypot rows whose
  out-of-fold probability of their *stamped* label is below 0.1 get weight 0. Out-of-fold
  because a memorizing model has low in-sample loss on everything it was fit to.
- *kNN label sanitization.* `k = 10` neighbours in seed_train (the trusted labelled
  set), normalizer fit on seed_train; a honeypot row is dropped when fewer than half
  its neighbours carry its stamped label.

**Expectations recorded in advance.** (i) kNN sanitization anchors to seed_train
labels, so copy-level poison — sitting among benign seed neighbours but stamped
malicious — should be caught; I expect it to **succeed** against A1 and to **hurt**
S0's `honeypot_only` learning (a family with no seed twins has no agreeing
neighbours). That would contradict the hypothesis that generic defenses fail
*because* the poison is "correctly labelled by the defender's own policy": the
policy's label is wrong, and a seed-anchored filter sees that. (ii) Loss-based
filtering with out-of-fold loss may do better than in-sample loss but is weaker where
poison is dense enough to be self-consistent. If the results say otherwise they are
reported as such.

**Evaluation.** Undefended, D1, loss filter, kNN filter on CICIDS A1 (jitter 0;
ratios 0.02/0.05/0.2, D1 at all seven), both models, 5 seeds; FPR/TPR recovery
(share of the undefended damage removed); S0 on synthetic per arm for utility;
wall-clock overhead per round; and the attacker cost (flows, packets, bytes, flow
time) at which the same FPR damage (>= +0.10) is first reached with and without D1.

**Amendment to §20, recorded before any defended run.** §20's evaluation set (A1 ratios
0.02/0.05/0.2) was written when the baseline threshold was miscalibrated. The calibration fix
(§19) moved A1's damage to >=10-20% poison (raw benign fidelity, new calibration: RF +0.002 /
+0.003 / +0.009 at 1% / 2% / 5%, +0.025 at 10%, +0.34 at 20%, +0.88 at 50%; XGBoost
+0.014 at 10%, +0.28 / +0.56 at 20% / 50% with a very large seed spread). Ratios below 10% now
show no undefended damage to recover, so the defended evaluation uses **ratios {0.05, 0.1, 0.2,
0.5}** (0.05 as a no-damage placebo), and D1 additionally at 0.8 and 0.9 for the
cost-to-damage measurement (XGBoost only; RF at those sizes is too slow). D1's parameters,
the generic baselines' parameters, the sensitivity protocol and its "not sensitive" criterion
are unchanged. The sensitivity grid and ablations run at ratio 0.5 (XGBoost), where the
undefended damage is largest. No defended result had been seen when this was written.

## 21. D1 and the generic baselines: results

> **Erratum (§24).** §21.3 and §21.7 say D1 needs "no reference set / no labelled reference set". That is
> inaccurate: D1 needs four numbers (the median of each cost component over trusted benign flows), where
> kNN needs the whole labelled seed set. §24 defines and measures a variant that needs no trusted data.

Setup as fixed in §20 and its amendment: CICIDS2017, A1 at raw benign fidelity (jitter 0, the
regime where A1 works), new calibration (`val_min_nn_distance = 0.1`), 5 seeds, 20 rounds, RF and
XGBoost, paired same-seed deltas against the control, final round. Code:
`src/dloop/defense/{d1_cost_weighting,generic}.py`; sweeps: `experiments/run_defense_sweeps.sh`;
report `experiments/phase0_defense_report.py` -> `results/phase0/defense/` (CSVs, `report.md`,
figures). 3 workers, because the machine had ~400 MB free beyond them (earlier 4-worker sweeps
crashed on memory).

### 21.1 Recovery: what each defense does to A1

Fixed-threshold FPR rise over control (recovery = share of the undefended damage removed;
2 sigma_control: RF 0.009, XGBoost 0.012). No recovery is quoted at 5% poison: there is no
undefended damage to recover.

| ratio | model | undefended | D1 (E*=8, g=2) | kNN sanitize | loss filter |
|---:|---|---:|---:|---:|---:|
| 0.2 | RF | +0.337 +/- 0.139 | +0.003 (99%) | +0.000 (100%) | +0.329 (2%) |
| 0.2 | XGB | +0.279 +/- 0.374 | -0.001 (100%) | +0.003 (99%) | +0.282 (-1%) |
| 0.5 | RF | +0.880 +/- 0.024 | +0.067 +/- 0.009 (92%) | +0.004 (99%) | +0.880 (0%) |
| 0.5 | XGB | +0.563 +/- 0.457 | +0.040 +/- 0.043 (93%) | +0.006 (99%) | +0.566 (0%) |
| 0.8 | XGB | +0.923 +/- 0.058 | +0.095 +/- 0.046 (90%) | not run | not run |
| 0.9 | XGB | +0.965 +/- 0.005 | +0.132 +/- 0.036 (86%) | not run | not run |

TPR under the recalibrated threshold follows the same pattern (RF at 50%: undefended -0.282,
D1 -0.036, kNN -0.087 +/- 0.128, loss -0.289; XGBoost at 90%: undefended -0.52, D1 -0.16).
At 20% poison D1 is inside 2 sigma of the control for both models; at 50% it leaves a residual
(+0.04 to +0.07) that is 7-8% of the undefended damage but larger than noise.

**Generic defenses vs the hypothesis.** The hypothesis was that generic defenses underperform
*because* the poison is "correctly labelled by the defender's own policy". It is half right:

- **Loss-based filtering fails, and for the predicted reason.** Its zero-weight fraction falls
  with poison density — 60% of poison dropped at 5%, 33% at 10%, 1.5% at 20%, 0% at 50% —
  because a dense block of identically-stamped rows teaches the auxiliary model its own label,
  so out-of-fold loss stops flagging it (unit-tested on toy blobs: `test_loss_filter_is_weaker...`).
  It recovers ~0% wherever there is damage.
- **kNN label sanitization does not fail — it is the strongest defense here (99-100%).** It
  anchors to the trusted seed labels rather than to the loop's own labels, so it sees exactly
  what the policy cannot: near-copy poison sits among *benign* seed neighbours but is stamped
  malicious (98.5% of A1 poison rows are dropped). The policy's label is wrong, and a
  seed-anchored filter can tell. §20 recorded this expectation before the run; the
  "generic defenses fail because the labels are policy-consistent" claim is false as a blanket
  statement and true only for defenses that learn from the poisoned data itself.

### 21.2 What each defense costs the honest loop (utility)

S0 (genuine attack rows), fixed threshold, final round: share of the undefended `honeypot_only`
TPR gain over control that survives (`utility_s0.csv`). `honeypot_only` is the family the
detector sees only through the decoy, i.e. the loop's whole point.

| dataset | ratio | D1 | kNN | loss filter |
|---|---:|---:|---:|---:|
| synthetic, RF / XGB | 0.05 | 12% / 10% | 45% / 42% | 99% / 100% |
| synthetic, RF / XGB | 0.2 | 45% / 58% | 74% / 78% | 100% / 100% |
| CICIDS2017, RF / XGB | 0.05 | 65% / 83% | 65% / 83% | 92% / 98% |
| CICIDS2017, RF / XGB | 0.2 | 52% / 66% | 51% / 66% | 100% / 97% |

D1 and kNN both cost the honest loop roughly **half** of what it would learn about a family
with no seed twins; the loss filter costs nothing and protects nothing. `seed_only` is
untouched by every defense. D1's weights explain the synthetic numbers: genuine synthetic
attack flows are cheap (mean D1 weight 0.10, vs 0.23 for benign and 0.84 for CICIDS attack rows),
because the synthetic generator was never given an attacker-cost profile. **How much D1 costs S0
therefore depends on whether real attacks are expensive relative to legitimate traffic; the
simulator cannot say.** That is the trade-off §20 stated in advance; it is real, and it is large.

### 21.3 Overhead

Mean seconds per round over rounds with honeypot data, against the model fit+score time
(`overhead.csv`): D1 **< 1 ms** (0%); kNN 0.07 s (4% RF, 6% XGBoost); loss filter 0.68 s
(30% RF, 56% XGBoost). D1 needs no reference set and no auxiliary model; kNN needs the trusted
labelled set at run time.

### 21.4 Attacker cost to reach the same damage

Damage target: fixed-threshold FPR rise >= 0.10 (`attacker_cost_to_damage.csv`).

| | first ratio reaching it | flows | packets | bytes | flow-time (s) |
|---|---:|---:|---:|---:|---:|
| undefended (RF, XGB) | 0.2 | 7,500 | 149,313 | 84.9 MB | 131,937 |
| D1, XGBoost | 0.9 | 270,000 (**36x**) | 5.18M (35x) | 2.84 GB (33x) | 4.78M (36x) |
| D1, RF | not reached at 0.5 (max rise +0.067) | > 30,000 (**> 4x**) | > 3.9x | > 3.8x | > 4.0x |

The multiplier is bracketed by the ratio grid, not a point: undefended crosses 0.10 between
ratios 0.1 and 0.2, D1/XGBoost between 0.5 and 0.9, so the cost increase is **between 4x and
~80x** in flows (36x at grid resolution); RF's is a lower bound (RF was not run beyond 0.5). D1
therefore raises the attacker's required effort by at least a factor of four, and by roughly
thirty-five for XGBoost at the resolution measured.

### 21.5 Sensitivity to the parameterisation — the pre-registered criterion is NOT met

Pre-registered (§20): D1 is "not sensitive" iff A1 FPR damage stays within 2 sigma_control
(0.012) over `E* >= 4, gamma >= 1`. XGBoost, ratio 0.5, jitter 0 (undefended +0.563):

| gamma \ E* | 2 | 4 | 8 | 16 | 32 |
|---:|---:|---:|---:|---:|---:|
| 1 | +0.340 | +0.081 | +0.053 | +0.030 | +0.015 |
| 2 | +0.084 | +0.060 | +0.040 | +0.025 | **+0.005** |
| 3 | +0.076 | +0.059 | +0.036 | +0.020 | **+0.003** |

**Criterion met: False** (2 of 12 configurations in the region; bold = inside 2 sigma). D1's
damage is monotone in both parameters — stronger with higher `E*` and `gamma` — and every
configuration in the region still removes **>= 86%** of the undefended damage (E*=4,gamma=1 the
weakest at 86%), but the residual at 50% poison is not negligible and scales with `E*`. The
honest reading: **D1 is insensitive in direction and sensitive in magnitude.** (At 20% poison
the default is already inside noise; this grid is deliberately at the largest ratio.) The
E* = 2, gamma = 1 corner recovers only 40%. The default (E* = 8, gamma = 2) was fixed before
any result and is not re-tuned.

Component ablation at the default (`E*=8, gamma=2`): packets-only +0.011 (inside 2 sigma),
depth-only +0.015, bytes-only +0.049, duration-only +0.066, all four +0.040. The equal-weight
geometric mean is **not** the best choice on this data: heavy-tailed benign flows with large
bytes or duration reach full weight under the combined effort, whereas packet count (and depth)
separates them better. This is reported, not acted on (no post-hoc re-tuning of a pre-registered
default). An earlier depth-only ablation silently never ran because two single-component tags
collided (`_cd`), and the resume logic treated it as done; the tags are now distinct, a test
guards it, and both single-component ablations were re-run.

### 21.6 The adversary's counter-move: padding to buy weight

`cost_padding = m` scales duration, packets and bytes before jitter; XGBoost, ratio 0.5:

| m | realized NN | undefended: weight / FPR rise | D1: mean weight / FPR rise | attacker bytes |
|---:|---:|---:|---:|---:|
| 1 | 0.011 | 1.00 / +0.563 +/- 0.457 | 0.23 / +0.040 +/- 0.043 | 3.2e8 |
| 2 | 0.135 | 1.00 / +0.021 +/- 0.020 | 0.31 / +0.007 +/- 0.004 | 6.4e8 |
| 8 | 0.331 | 1.00 / -0.003 | 0.48 / -0.001 | 2.6e9 |
| 32 | 0.532 | 1.00 / -0.005 | 0.90 / -0.004 | 1.0e10 |

The tension §20 asserted holds: padding raises D1's weight (0.23 -> 0.90) but moves the poison
away from copy fidelity (realized NN 0.011 -> 0.53) and the damage is gone. **But the padded
attack also fails against the undefended loop** (+0.021 at m = 2), so padding is not evidence
for D1 — the fidelity break does that on its own. The attacker's effective counter to D1 is
not padding but *volume* (§21.4: 4x-80x more flows of copy-level traffic). Padding merely
shows the cheaper evasion of D1 is not available.

### 21.7 Verdict, and what is not shown

- D1 removes 86-100% of A1's damage wherever there is damage, at ~zero overhead, using only
  cost — no labelled reference set, no auxiliary model.
- **It is not clearly better than kNN sanitization on this evaluation.** kNN is stronger at
  50% poison (99% vs 92-93%) and costs about the same honest-loop utility; D1 is free to run,
  independent of seed labels, and is the only one of the two with an attacker-cost account.
  A fair summary is "comparable protection at comparable utility cost; different assumptions".
- The **loss filter is not a serious baseline once poison is dense**, and that failure is the
  predicted one.
- Not shown: any adaptive attacker against kNN (an attacker placing poison near seed *attack*
  neighbours would need attack-like traffic, so it would not obviously raise FPR, but this is
  untested); the sensitivity grid is XGBoost at one ratio; RF was not run beyond 0.5;
  everything is CICIDS2017 (degenerate, §16) at raw benign fidelity, the worst case for A1; the
  cost features are flow-level, `depth` is a stand-in, and the simulator has no real honeypot
  session logs, so D1's utility cost on a real deployment is unknown (§21.2).

## 22. The second A1 mechanism, at a distance: what it is, and what it is not

Prompted by a correction from review, checked against the data. **Correction to earlier text:**
a chat summary of §17 said TPR under the recalibrated threshold collapses "only at copy-level
fidelity". That is wrong for RF: at ratio 0.2 (old-calibration control 0.810 +/- 0.028) TPR is
0.670 at jitter 0 and 0.706 at jitter 1.5 (realized NN 1.05, -0.103, ~3.7 sigma), and 0.736 /
0.749 / 0.756 / 0.759 at realized 0.25 / 0.17 / 0.014 / 0.09. §17 recorded the far drop but the
summary contradicted it. Also confirmed: XGBoost fixed-threshold FPR *rises* with distance under the
old calibration (0.046 at jitter 0.01 -> 0.067 at 1.5, control 0.044).

**Method.** Same-seed paired deltas against the control, CICIDS2017, 5 seeds, final round.
Far-distance arms at jitter 1.5 (realized NN ~1.06), poison ratios 0.02 / 0.05 / 0.2 / 0.5, run under
both calibrations: `a1` (benign rows + jitter, stamped malicious), `a1truth` (the same rows, true
label), `s0j` (attack rows + the same jitter, stamped malicious), `s0` (attack rows), and **`junk`**
(each feature drawn independently from the pooled benign + attack marginals: realistic per-feature
ranges, no correlations, resembling neither class; realized NN to trusted benign: median 0.64, p5
0.44, p95 0.90), stamped malicious. `junk` is the direct test of "send the honeypot arbitrary bulk
volume". Code `experiments/phase0_far_report.py`, results `results/phase0/far/`.

**On the test design.** A matched arm that injects the same row count from the attack
distribution has the *same* class-prior shift as `a1` and no benign-label conflict. If an effect
appears in `a1` but not in the matched arm, the difference is the benign-label conflict and it is
*not* prior shift; prior shift predicts the effect in both. (Earlier wording of this test had the
inference reversed; the conclusions below use the correct direction.)

### 22.1 Fixed-threshold FPR: a volume effect, gated by the threshold

Old calibration (control FPR 0.046; 2 sigma: RF 0.030, XGBoost 0.020), FPR rise, ratios 0.02 /
0.05 / 0.2 / 0.5:

| arm | RF | XGBoost |
|---|---|---|
| a1 (far) | +0.022 / +0.031 / +0.037 / +0.042 | +0.003 / -0.002 / +0.024 / +0.035 |
| **junk** | **+0.030 / +0.031 / +0.045 / +0.047** | +0.015 / +0.017 / +0.018 / +0.025 |
| s0j | +0.003 / +0.020 / +0.031 / +0.035 | -0.005 / -0.004 / +0.004 / +0.019 |
| s0 (attack rows) | -0.003 / +0.009 / +0.027 / +0.029 | +0.021 / +0.028 / +0.029 / +0.040 |

The old-calibration flat effect **is** volume: `junk` — rows that resemble neither class —
reproduces it at the same size as `a1` (RF +0.045 vs +0.037 at 20%), it grows with the poison
*ratio* (rank correlation with ratio 0.5 RF / 0.7 XGBoost at fixed distance) and not with distance,
and `s0` (attack rows, no benign conflict) shows it too. This is the reviewer's "prior shift", and
**§19.2's verdict that the flat FPR effect is "not class-prior shift" was too strong**: it rested on
`s0`/`s0j` at one jitter, and `s0` places its rows in attack regions, so it understates the intrusion
of malicious-stamped mass into benign-populated regions that `junk` and `a1` produce.

**But it is gated by calibration.** Under the honest calibration (tau = 0.1; 2 sigma RF 0.009,
XGBoost 0.012) every arm is inside noise: `a1` +0.002 / -0.001 / +0.004 / +0.011 (RF; the +0.011 is
barely over 2 sigma), `junk` +0.002 / +0.001 / +0.004 / +0.003, XGBoost within +/- 0.006 for all
arms. A threshold set too low turns any small score shift into FPR; a threshold set honestly does
not. On the non-degenerate synthetic data, where the control is already at target (FPR 0.0085) and
the arm is genuine attack rows, the same volume effect is small but real: S0 raises fixed FPR to
0.0161 at 20% and 0.0239 at 50% (RF), i.e. about 1.6x and 2.4x the 0.01 target. So bulk volume is a real
channel even with a well-set threshold, at a few times the target FPR, and it is exposed
catastrophically only when calibration is naive; on degenerate data, naive calibration is the
default (§19.1: 94% of validation rows had a training twin).

### 22.2 Recalibrated-threshold TPR: not volume — this is the RF-only channel

RF (2 sigma 0.061), TPR change, ratios 0.02 / 0.05 / 0.2 / 0.5 (identical under both calibrations):

| arm | RF |
|---|---|
| **a1 (far)** | **-0.045 / -0.064 / -0.103 / -0.095** |
| **junk** | **+0.024 / +0.024 / +0.015 / +0.013** |
| s0j | -0.002 / -0.017 / -0.056 / -0.043 |
| s0 | n/a / +0.058 / +0.079 / n/a |
| a1truth | +0.028 / +0.014 / -0.008 / -0.118 +/- 0.085 |

The effect scales with the poison ratio (rank correlation 0.54, saturating near -0.10 from 20%),
not with distance (0.28, weakly positive). It is **not** reproduced by pure volume: `junk` at up to
50% of the training set leaves TPR unchanged. It needs the poison to sit near benign mass:
benign-origin rows at any distance (`a1`), and attack rows only when the jitter is large enough
(1.5) to throw a fraction of them into benign-populated regions (`s0j` about half of `a1`;
essentially zero at jitter 0.7, §19.2). Mechanism: malicious-stamped rows inside benign-populated
regions lift benign scores slightly; a recalibrated threshold rises to hold FPR at 1%, and TPR pays.
XGBoost is immune (`a1` +0.002 to -0.007 at every ratio): RF's leaf probabilities respond to the
local label mix; XGBoost's regularised additive output does not. **This model dependence is a
finding in its own right and is not averaged away.** (One caution: benign-labelled noisy bulk
(`a1truth`) can *also* lower recalibrated TPR at high ratio (RF -0.118, XGBoost -0.180 / -0.190),
so recalibrated TPR is sensitive to diluting the training set with noisy rows generally.)

### 22.3 The mechanisms, named and sized

| | needs | size | shows in | models |
|---|---|---|---|---|
| **M1 label conflict at copy fidelity** | near-exact reproduction of trusted benign (realized NN <~ 0.011-0.014); >= 10-20% poison (honest calibration) | catastrophic: FPR +0.34..+0.88 (RF), bimodal for XGBoost (§19.1) | fixed FPR; TPR under recalibration (RF -0.14 at 20%, -0.28 at 50%) | RF, XGBoost |
| **M2a malicious-stamped bulk volume** ("prior shift") | no fidelity; volume; any rows | +0.02..+0.05 FPR under a mis-set low threshold (both models); ~0 under an honest one; 1.6x / 2.4x the target FPR at 20% / 50% on well-calibrated synthetic | fixed-threshold FPR | RF, XGBoost |
| **M2b benign-origin label conflict at a distance** | rows near benign mass (not reproduced by junk); scales with ratio | RF TPR -0.05..-0.10 (saturating from 20%) | recalibrated TPR | **RF only** |

### 22.4 Defenses, per mechanism (honest calibration; recovery of the undefended damage)

| mechanism | undefended | D1 (E*=8, g=2) | kNN sanitize | loss filter |
|---|---|---|---|---|
| M1, FPR (§21.1) | +0.34 / +0.88 (RF, 20% / 50%) | 99% / 92% | 100% / 99% | 2% / 0% |
| **M2b, RF TPR drop, 20% / 50%** | -0.103 / -0.095 | **-0.085 / -0.104 (17% / -9%)** | **-0.010 / -0.027 (90% / 72%)** | -0.100 / -0.099 (3% / -4%) |
| M2a (junk), honest calibration | none to recover (FPR ~0, TPR +0.01..+0.03) | n/a | n/a | n/a |

- **kNN catches both label-conflict regimes** (98.6% of copy-level poison dropped, 93% at jitter 1.5,
  85% of junk).
- **The loss filter misses both**, because dense poison is self-consistent (§21.1).
- **D1 does not suppress M2b.** The hypothesis that both mechanisms are cheap and cost weighting should
  kill both fails for the second: jitter and junk *inflate* the very cost features D1 reads
  (packets, bytes, duration), so far poison gets **more** weight than copy-level poison (mean weight
  0.44 vs 0.23; junk 0.41; effective ratio 0.31 at nominal 0.5), and it is D1's residual +0.085 /
  +0.104 TPR drop. The cost features are also model features (§20), so the same padding that raises
  weight also moves the row, and here it moves it into the noise cloud that M2b exploits, not away
  from it. D1 protects against M1 only. Clean negative.
- Not run: defenses under the old calibration (where M2a's FPR effect lives), and any defense
  against M2b other than these three.

### 22.5 Corrections and artifacts

- The reviewer's "TPR collapses far from benign" and "XGBoost FPR rises with distance" are right
  and are recorded above. The reviewer's "prior shift" is right for FPR under a mis-set threshold
  and wrong for the RF TPR channel, where `junk` (pure volume) has no effect.
- `results/phase0/mechanism/` was regenerated: its loader had averaged defended S0 jobs into the `s0`
  arm (the §19.2 text used the correct values; the committed CSV/figure did not). The loop report's
  loader had the same bug; both now select undefended, default-calibration runs only.
- The consolidated artifacts requested for reproducibility are `results/phase0/export/rounds.csv.gz`
  (every per-round row of all 1,850 jobs), `summary.csv` (final-round mean/sd per configuration and
  paired delta) and `damage_curve.csv` (A1 damage vs realized distance, both calibrations),
  generated by `experiments/phase0_export.py`. Files under those names did not exist before; the raw
  per-round rows were already committed as per-job CSVs.

## 23. The mechanism restated: one mechanism, two channels (supersedes §22.3's naming)

§19 and §22 named up to three mechanisms while the evidence was still arriving. The matched
controls settle it: **prior shift is null as a mechanism.** What remains is one mechanism acting
through two channels.

**The mechanism: label conflict.** Rows that sit in benign-populated regions of feature space, stamped
malicious by the auto-labeler ("everything the honeypot sees is malicious"). It does not need the
poison to be *far* from anything, only that the stamped label contradicts the neighbourhood.

**Prior shift is null — the two matched controls, RF recalibrated TPR, ratio 0.2, realized NN
~0.56, 5 seeds (`results/phase0/mechanism/`):**

| arm | what it isolates | TPR change | paired t |
|---|---|---:|---:|
| **A1** benign rows + jitter, stamped malicious | the effect | **-0.109 +/- 0.038** | **-6.4** |
| a1truth: the same rows, true label | rows without the label conflict | +0.014 +/- 0.029 | +1.1 (n.s.) |
| s0j: attack rows + the same jitter, stamped malicious | same volume, same prior shift, no conflict | -0.002 +/- 0.029 | -0.2 (n.s.) |
| junk: marginal-shuffled bulk, stamped malicious (jitter-1.5 run, ratio 0.2) | volume alone | +0.015 +/- 0.033 | n.s. |

Both null controls come back empty. The same rows without the wrong label do nothing; the same
volume and the same class-prior shift, with the labels correct for what the rows are, do nothing.

### The two channels

| | FPR channel (fixed threshold) | TPR channel (recalibrated threshold) |
|---|---|---|
| **needs** | **copy fidelity** (realized NN <~ 0.011-0.014); >= 10-20% poison (honest calibration) | nothing beyond rows in benign-populated regions; **works at every distance tested** |
| **size** | RF **+0.337** at 20%, **+0.880** at 50% (XGBoost +0.279 / +0.563, bimodal across seeds) | RF **-0.109** at 20%, saturating near -0.10 from 20% |
| **at distance** | +0.011 +/- 0.001 (RF, realized 0.56, t ~ +24): real, ~+1 point of FPR (0.007 -> 0.018), small next to 30-90 points at copy fidelity | as above |
| **XGBoost** | as above | **none**: A1 +0.017 at realized 0.56 and -0.007 at 1.06 |

**Correction to a reading of the tables.** XGBoost's "-0.032" at 20% is the contrast `a1 - s0j`
(0.017 minus a matched arm that happens to *raise* TPR by 0.049), not a TPR change. XGBoost has no
TPR channel; the TPR channel is **RF-only**, and that model dependence is reported as its own
finding: RF's leaf probabilities respond to the local label mix, XGBoost's regularised additive
output does not.

**Both floors, and what the shift shows.** The round-0 threshold was calibrated on validation rows
that mostly have a training twin; under it the control FPR was 0.046 +/- 0.015 against a 0.01 target,
and the distance-FPR effect (RF, ratio 0.2, realized 0.56) read **+0.054**. Calibrated on twin-free
rows (§19.1, tau = 0.1) the control is 0.007 +/- 0.005 and the same effect is **+0.011**: the old
baseline inflated it **~5x**, and inflated the copy-fidelity threshold from ~10-20% to 1-2% poison.
The need to discard 94% of benign validation rows to get an honest operating point is itself
evidence for the degeneracy finding (§16): nearly every held-out benign flow has a near-copy in
training.

**Kept, demoted: volume.** Under the old (too-low) threshold a `junk` arm reproduces the flat FPR
effect at A1's size (RF +0.045 vs +0.037 at 20%): any bulk stamped malicious moves benign scores
enough to cross a threshold set too low. It is a *calibration fragility*, gone under the honest
threshold (junk +0.002 to +0.004), and not a distinct attack mechanism. Separately, on the
well-calibrated non-degenerate synthetic data the *honest* loop (S0, genuine attacks, correct
labels) raises fixed-threshold FPR from 0.0085 to 0.0161 at 20% and 0.0239 at 50% honeypot share:
a small cost of retraining on more positives, present with no attacker at all.

### Named finding: the policy-consistency blind spot

**Generic poisoning defenses that check labels against the loop's own data fail structurally
here.** The poison is wrong against ground truth (benign flows stamped malicious) but *consistent
with the defender's own labelling policy*, and it is dense, so a model fit on the loop's data learns
that label as its own. The loss-based filter recovers essentially nothing where there is damage:

| ratio | RF recovery | XGBoost recovery | share of poison it drops |
|---:|---:|---:|---:|
| 0.05 | (no damage) | (no damage) | 60% |
| 0.10 | -10% | 18% | 33% |
| 0.20 | 2% | -1% | 1.5% |
| 0.50 | 0% | 0% | 0% |

It is not that the label is "correct" (it is not) and not that low loss is intrinsic: out-of-fold
loss flags sparse flips and stops flagging them as the poison becomes self-consistent (§21.1, and a
unit test on toy blobs). The defenses that work are anchored *outside* the loop: kNN against the
trusted seed labels recovers 99-100% because it sees what the policy cannot, that near-copy poison
sits among benign seed neighbours. **The failure is of label-consistency checks, not of generic
defenses in general.**

## 24. D1 on the recovery/utility frontier: protocol fixed before the runs

Prompted by review. (E* = 8, gamma = 2) is one point, kNN sanitization matches its recovery,
and D1 keeps the least of the honest loop (synthetic RF, ratio 0.05, `honeypot_only` gain
retained: loss filter 99%, kNN 45%, D1 12%). This section fixes the frontier protocol
**before** any of these runs.

**Two corrections to earlier text (mine).**
(a) §21.3 and §21.7 said D1 needs "no reference set / no labelled reference set". That is
inaccurate: D1 needs **four numbers** — the median of each cost component over the benign
rows of seed_train (its unit of effort). kNN needs the **whole labelled seed set**, retained
and queried per batch. A variant needing no trusted data at all is defined below and measured.
(b) The 0.10 (synthetic) vs 0.84 (CICIDS) mean D1 weight on S0 rows at identical parameters is
not the absolute-vs-relative threshold problem: E* is already in units of each dataset's own
benign median (§20). It is **cost separability** — how much more the genuine attack rows cost
than benign flows in that dataset. Median effort (benign / attack): CICIDS 0.48 / 11.8;
synthetic 1.12 / 0.98. On synthetic, cost cannot tell A1's poison (benign) from S0's genuine
attack rows, so no cost-based weighting can protect against one and preserve the other there;
the synthetic generator was never given an attacker-cost profile. The separability is measured
(AUROC of effort separating benign from attack) rather than asserted.

**Variants** (`src/dloop/defense/d1_cost_weighting.py`, all else as §20):

- `D1` — E* in units of a median benign flow (the pre-registered form).
- `D1q` — quantile-anchored: `E* = Q_q` of the effort of the benign seed rows, `q in {0.5,
  0.75, 0.9, 0.95, 0.99}`. Normalises the *tail* per dataset rather than the median.
- `D1fixed` — fixed reference units `r = (1 s, 10 packets, 1000 bytes, 3 exchanges)` with no
  trusted data (within a factor of ~2-3 of both datasets' medians), `E* in {4, 8, 16, 32}`,
  gamma = 2.
- `Uniform(w)` — every honeypot row at weight `w in {0.05, 0.1, 0.25, 0.5}`: the **no-skill
  line**. A D1 setting is only doing something cost-aware if it beats this.

**Grid.** `D1`: `E* in {2, 4, 8, 16, 32}` x `gamma in {1, 2, 3}` (15). `D1q`: the five quantiles x
`gamma in {1, 2}` (10). XGBoost for the full grid (RF is ~3x slower); RF re-checks on the
points that matter.

**Axes** (5 seeds, paired same-seed deltas against the control, honest calibration for CICIDS):

- **Recovery** `R = 1 - mean(dFPR_defended) / mean(dFPR_undefended)`: A1 at raw benign fidelity
  (jitter 0), ratio 0.5, fixed threshold. Ratio 0.5 is where the undefended damage is largest.
- **Retention** `U = mean(gain_defended) / mean(gain_undefended)`: S0 on **synthetic** (the
  dataset that can carry a learning claim), `honeypot_only` TPR gain over the control, ratios
  0.05 and 0.2, fixed threshold. `seen_both` gains are ~+0.01 and are recorded raw with a warning
  that their ratio is noise-dominated.

**Dominance.** Setting X dominates kNN iff `R_X >= R_kNN` and `U_X >= U_kNN` (by mean). Because
5 seeds is few, the **seed-bootstrap probability** of that joint event is reported; X *clearly*
dominates if it is >= 0.9. A setting that dominates by mean only is reported as such. Dominance
is checked on the grid and then re-checked out-of-grid (RF at the same points) before any claim,
because best-of-grid selection is biased.

**Overhead** is measured at full precision from the recorded `defense_seconds` per round, as a
ratio D1/kNN with a bootstrap interval over jobs. The claim "comparable protection at far lower
overhead, needing less trusted data" is stated as measured numbers whichever way dominance
falls, not as a consolation.

### 24.1 Results

Code `experiments/phase0_frontier_report.py`, sweeps `experiments/run_frontier_sweeps.sh` and
`run_frontier_followup.sh`, results `results/phase0/frontier/` (`frontier_points.csv`,
`dominance.csv`, `frontier.png`, `report.md`). XGBoost, 5 seeds, CICIDS at tau = 0.1. Recovery is
A1 at raw benign fidelity, ratio 0.5 (0.9 where run). Retention is the share of the undefended S0
`honeypot_only` gain kept, measured on synthetic (ratios 0.05 / 0.2) **and** on CICIDS (ratio 0.2).
The first version measured recovery and retention on different datasets; a per-dataset-normalised
defense can look better than a dataset-agnostic one that way, so the CICIDS retention axis was added
and is the like-for-like comparison.

| defense | recovery r0.5 | recovery **r0.9** | retention syn 0.05 / 0.2 | retention **CICIDS** 0.2 |
|---|---:|---:|---:|---:|
| loss filter | -0.5% | n/a | 100% / 100% | 98% |
| **uniform w=0.05** (no skill) | 99.8% | **52%** | 71% / 96% | 71% |
| **uniform w=0.1** (no skill) | 98.9% | **43%** | 91% / 98% | 74% |
| uniform w=0.25 (no skill) | 48.9% | n/a | 98% / 99% | 81% |
| kNN sanitize | 98.9% | 99.1% | 42% / 78% | 66% |
| D1 (E*=8, g=2), pre-registered | 92.9% | 86.3% | 10% / 58% | 66% |
| D1 (E*=8, g=1) | 90.6% | n/a | 85% / 97% | 67% |
| D1q q=0.99, g=1 | 99.7% | 93.8% | 96% / 98% | 65% |
| D1q q=0.99, g=2 | 100% | 98.7% | 67% / 94% | 65% |
| D1fixed E*=8, g=2 (**no trusted data**) | 94.2% | n/a | 56% / 93% | 65% |
| D1fixed E*=16, g=2 | 97.6% | n/a | 13% / 65% | 65% |

**1. No setting of the pre-registered D1 dominates kNN.** Across the 15-point (E* x gamma)
grid every setting is either weaker on recovery or keeps less on one axis; the pre-registered point
(E* = 8, gamma = 2) is the worst on synthetic retention (10% at ratio 0.05, 12% for RF). It is a
trade-off curve, not a dominance.

**2. The apparent wins are a cross-dataset artifact.** The quantile-anchored D1q (q = 0.99) *does*
dominate kNN, with P = 1.00 on both synthetic retention axes. It does **not** on the like-for-like
CICIDS axis: 65% vs 66%. Reason: `E*` is a quantile of each dataset's own benign effort, so it is huge
on CICIDS (heavy benign tail; attack rows weigh 0.02-0.13 on average) and small on synthetic (thin tail;
attack rows weigh 0.27-0.41). D1q gets its synthetic retention by weighting nearly everything at
0.3-0.4 there, not by telling attacks from poison. The direct measurement: **cost separates
benign from attack flows on CICIDS (AUROC of effort 0.81) but not on synthetic (0.46; attack
flows are slightly *cheaper* than benign)**. That is what the 0.10 vs 0.84 mean-weight gap was;
E* was never absolute (it is in units of each dataset's benign median), so the gap is cost
separability and not parameterisation.

**3. The no-skill baseline is a strong comparator at ratio 0.5 and fails at ratio 0.9.** Down-weighting
every honeypot row by the same factor caps the poison's *effective* share below the ~10% damage
onset, so at ratio 0.5 uniform w = 0.1 matches kNN's recovery (98.9%) while keeping more of the
honest loop (91% / 98% on synthetic, 74% on CICIDS vs kNN's 42% / 78% / 66%). It stops working when the
nominal ratio rises: at ratio 0.9 it recovers **43%** (w = 0.1) and **52%** (w = 0.05), where kNN
recovers 99% and D1q (q = 0.99, g = 2) 99%. A defense that has to work at a poison
ratio the defender does not control cannot be a blanket cap; it has to be selective.

**4. Same-dataset verdict.** On CICIDS, where both axes come from one dataset, kNN and every
D1q / D1fixed point keep ~65-66% of the honest gain. (An earlier version of this sentence said uniform
keeps more only by giving up recovery. That is wrong at ratio 0.5: uniform w=0.05 / 0.1 keep 71% / 74%
*and* recover 99.8% / 98.9%; it gives up recovery only at ratio 0.9. See §25.1(2).)
and recover 94-100%. D1q (q = 0.99) at ratio 0.9 recovers 94% (g = 1) / 99% (g = 2) against kNN's 99%.
**Cost weighting reaches comparable protection and comparable retention to kNN sanitization on CICIDS;
it does not dominate it.** The RF check agrees (recovery r0.5: kNN 99.5%, D1q 98.9%, uniform 95.7%,
pre-registered D1 92.4%; synthetic retention 0.05 / 0.2: kNN 45% / 74%, D1q 90% / 97%, D1 12% / 45%).

**5. What is measured about D1's actual advantages.**

- **Overhead.** D1 costs 0.000216 s per round; kNN 0.168 s at ratio 0.5 (kNN's cost grows with the
  poison volume it must query; the 0.069 s seen at lower ratios is the same effect): a ratio of **781x**
  (95% bootstrap 735x-837x). Against the fit time: 0.014% vs 14.7% (XGBoost). The loss filter costs
  53%.
- **Trusted data.** D1 needs four numbers (the benign median of each cost component), D1q one
  quantile of the benign effort, kNN the whole labelled seed set at run time. **D1fixed needs no trusted
  data at all** and still recovers 94.2% (E* = 8) - 97.6% (E* = 16) at ratio 0.5 with CICIDS retention 65%,
  i.e. kNN-level, at ~0 overhead. It was run only at ratio 0.5 (not 0.9).
- **Attacker cost.** §21.4: >= 4x-36x more flows for the same damage.

**6. The claim, as measured.** Cost-of-influence weighting is **not** a Pareto improvement over kNN
sanitization. It is a comparable-protection, comparable-utility defense with ~800x lower overhead, needing
either four benign summary statistics or (D1fixed) no trusted data, and it forces the attacker to spend
at least four times the flows. The pre-registered parameterisation (E* = 8, gamma = 2) is a poor point on
its own frontier, and the criterion that D1 be insensitive to parameterisation was not met (§21.5).

**Not established.** The D1q results are best-of-grid over a post-hoc variant (10 settings): they were
re-checked out of grid on RF and at ratio 0.9, but a selection bias remains. D1fixed was not run at 0.9.
The retention axes are S0 on synthetic (learning claim, but cost carries no class signal there) and
CICIDS (memorization, §16); no dataset has both a learning claim and a cost signal. kNN and the loss
filter were not run at the same grid of ratios as D1. The synthetic generator has no attacker-cost profile.

## 25. What the frontier establishes, and the stronger no-skill baseline

### 25.1 Three findings, stated plainly

**(1) Most of D1's protection at ratio 0.5 comes from down-weighting honeypot data at all, not from
cost discrimination.** A defense that uses no cost information at all — uniform weight 0.05 on every
honeypot row — recovers 99.8% of A1's damage at ratio 0.5; D1 dominates it in **0 of 87** (setting,
retention-axis) cases. D1 does retain more of the honest loop on the synthetic axes (D1q q=0.99 g=1:
0.961 vs 0.711 at S0 ratio 0.05), so it is not worthless there, but that retention is not evidence of
discrimination: see (2).
*Caveat this finding needs, added on review of the data:* the dominance test used recovery at ratio 0.5
only. At ratio 0.9 the fixed uniform weights fail (recovery 52% at w=0.05, 43% at w=0.1) while D1q
(q=0.99, g=2) recovers 99%, D1q g=1 94%, and kNN 99%. A fixed uniform weight is a no-skill baseline only
*at one poison ratio*; the correct no-skill comparator is the one defined in 25.2.

**(2) D1's clean win over kNN is on the dataset where its signal does not exist.** Effort separates
attack from benign flows with AUROC **0.461 on synthetic** (below chance: attack flows are slightly
cheaper than benign) and 0.809 on CICIDS. D1q dominates kNN (P = 1.0) only on the synthetic retention
axes; on CICIDS, where effort does carry signal, **no D1 variant dominates kNN**, and every D1 variant
sits at 0.64-0.67 retention regardless of E* or gamma, **worse than uniform w=0.05 / 0.1 (0.705 / 0.741)**
at the ratio-0.5 operating point. (§24.1 said uniform keeps more "only by giving up recovery"; that was
wrong at ratio 0.5, where uniform keeps more *and* recovers 99.8% / 98.9%. It gives up recovery only at
ratio 0.9 or at larger weights.)

**(3) The pre-registered insensitivity criterion of §20 failed.** "Not sensitive iff A1 FPR damage stays
within 2 sigma_control over E* >= 4, gamma >= 1": **2 of 12 configurations** met it (E*=32, gamma=2,3).
Reported as a failed pre-registered test. The criterion is not revised. (§21.5 records the grid; damage
falls monotonically with E* and gamma and every configuration in the region still removed >= 86%, but
that is a description of how it failed, not a redefinition of the test.)

### 25.2 A stronger no-skill baseline, fixed before it is run

Fixed uniform weights protect only at the poison ratio they were tuned for. The bar D1 has to clear is a
no-skill defense that works at *any* ratio: **`ShareCap(c)`** caps the honeypot's *effective share* of the
training set at `c` by giving every honeypot row the same weight
`w = min(1, c/(1-c) * n_seed / n_honeypot)`, recomputed at each retrain, so it needs no knowledge of the
poison ratio and uses no cost or label information. With `c` below the ~10% damage onset it should
protect at every ratio; and when the honest honeypot share is below `c` it does not bind at all
(retention 100%), so it is expected to **retain more than any fixed-weight defense**.

**Prediction, recorded before the runs:** ShareCap protects at ratios 0.5 and 0.9 and dominates the
pre-registered D1 and probably every D1 variant on retention; the only thing D1 could still contribute is
selectivity that ShareCap lacks. Caps `c in {0.03, 0.05, 0.08}`; A1 at ratios 0.5 and 0.9 (CICIDS,
XGBoost), S0 on synthetic (0.05 / 0.2) and CICIDS (0.2), 5 seeds, same axes as §24.

### 25.3 ShareCap result: the prediction held

Recorded prediction (25.2): ShareCap protects at ratios 0.5 and 0.9 and dominates D1 on retention. Result
(XGBoost, 5 seeds, `results/phase0/frontier/`):

| defense | recovery r0.5 | recovery r0.9 | retention syn 0.05 | retention syn 0.2 | retention CICIDS 0.2 |
|---|---|---|---|---|---|
| ShareCap c=0.03 | 1.003 | 1.001 | 0.993 | 0.979 | 0.737 |
| ShareCap c=0.05 | 0.999 | 1.000 | 0.998 | 0.986 | 0.807 |
| ShareCap c=0.08 | 0.992 | 0.995 | 1.000 | 0.994 | 0.834 |
| uniform w=0.05 | 0.998 | 0.522 | 0.711 | 0.960 | 0.705 |
| kNN | 0.989 | 0.991 | 0.423 | 0.784 | 0.658 |
| D1 (E*=8, g=2) | 0.929 | 0.863 | 0.101 | 0.580 | 0.660 |
| D1q q=0.99 g=1 | 0.997 | 0.938 | 0.961 | 0.983 | 0.645 |

Dominance over each ShareCap cap, by mean and at both ratios: **0 of 87** cases for every D1 variant, kNN and
uniform w=0.05; only uniform w=0.1 shows 2 of 87 against kNN. ShareCap needs no cost, label or feature
information, no trusted data, and no knowledge of the poison ratio. It beats every D1 variant on CICIDS
retention (0.74-0.83 vs 0.645-0.66) and on synthetic retention, and matches recovery at both ratios.

**Consequence: D1 does not earn its claim over the right no-skill baseline.** Cost discrimination is not
shown to add anything beyond capping the honeypot's effective share. Caveat: ShareCap's CICIDS retention
depends on the cap (0.74-0.83), and a cap is a tuning knob whose safe range (below the ~10% damage onset) was
taken from the A1 results themselves; it is not a free lunch against an adversary that also knows the cap
(under a cap the attacker's influence is bounded, but so is the honest loop's).

### 25.4 Step 1 (data check) and the honest D1 statement

**Data.** The local CICIDS2017 files (MachineLearningCVE) carry 79 columns, of which only `Destination Port`
is identifier-like: no source/destination IP, Flow ID or timestamp. Sessions cannot be built and are not
faked from file order. The timestamped `GeneratedLabelledFlows` release is form-gated and was unreachable
when checked; obtaining it is the user's action. Step 2 (session-level D1) is therefore not run.

**Flow-level diagnostic (motivates, does not test, the session hypothesis).** Under D1's default, 25% of DoS
Hulk flows have weight < 0.05, and DDoS/PortScan/FTP-Patator are mostly cheap per flow, but Hulk's mean weight
is 0.74. CICIDS retention stays ~0.64-0.66 while mean attack weight ranges 0.04-0.87, whereas uniform's
retention scales with weight; at equal mean weight D1 keeps ~6 points less. The ceiling seems to come from
*which* flows are discarded. Whether per-session aggregation fixes this is a hypothesis, untested.

**Statement of D1 as it stands.** (a) Protection comparable to kNN sanitization at ~781x lower overhead
(0.000216 vs 0.168 s/round; bootstrap 735-837x). (b) D1/D1q need only four benign summary medians; only
D1fixed needs no trusted data. (c) Its advantage over a fixed uniform weight appears at high poison ratios
(0.9), not low ones, but (d) it does not beat ShareCap at any ratio. (e) Flow-level cost proxies are
insufficient on CICIDS. (f) Hypothesis, not established: honeypot session logs (commands, auth attempts,
downloads, protocol depth) carry the effort signal flow summaries lose, which is a research reason for the
live Cowrie testbed.

### 25.5 The ShareCap cap-sensitivity curve, reported whole

The safe cap used in §25.2-25.3 (0.03-0.08) was picked from the A1 damage-onset results, which is circular as
a design justification even though the results themselves are not circular. The fix is to report the whole
curve rather than a chosen range. Full sweep, `c in {0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3, 0.5}`,
XGBoost, 5 seeds, paired last-round (round 20) FPR/TPR against the matched undefended run per seed:

| cap | recovery r0.5 (n) | recovery r0.9 (n) | retention CICIDS 0.2 | retention synthetic 0.05 | retention synthetic 0.2 |
|---|---|---|---|---|---|
| 0.01 | 0.991 (5) | 0.995 (5) | 0.657 | 0.945 | 0.884 |
| 0.02 | 0.989 (5) | 0.995 (5) | 0.671 | 0.977 | 0.913 |
| 0.03 | 0.991 (5) | 0.994 (5) | 0.653 | 0.987 | 0.922 |
| 0.05 | 0.988 (5) | 0.993 (5) | 0.752 | 0.996 | 0.937 |
| 0.08 | 0.981 (5) | 0.989 (5) | 0.781 | 1.000 | 0.957 |
| 0.10 | 0.965 (5) | 0.982 (5) | 0.830 | 1.000 | 0.969 |
| 0.15 | 0.610 (5) | 0.778 (5) | 0.911 | 1.000 | 0.980 |
| 0.20 | 0.483 (5) | 0.696 (5) | 1.000 | 1.000 | 1.002 |
| 0.30 | 0.197 (5) | 0.525 (5) | 1.000 | 1.000 | 1.000 |
| 0.50 | 0.000 (5) | 0.402 (5) | 1.000 | 1.000 | 1.000 |

Retention rises monotonically with the cap (an undefended, un-capped loop is the limit), as it must: a looser
cap lets more honest honeypot signal through. Recovery holds essentially flat (0.96-0.99) through c=0.10 and
then falls off a cliff between 0.10 and 0.20, reaching zero protection at c=0.50 for ratio 0.5 (the cap no
longer binds once it is at or above the actual poison share, so ShareCap degenerates to the undefended loop
by construction, not by failure of the mechanism). **The right cap depends on where damage onset is for the
given model and dataset — there is no cap that is simultaneously maximally protective and maximally
retentive, and this curve is what a deployer would need to tune against, not a single default.** The values
used in §25.2-25.3 (0.03-0.08) sit inside the flat, near-total-recovery region for this model and dataset;
that is a post-hoc justification of the earlier choice, not evidence that the same range is safe elsewhere
(e.g. under XGBoost, whose FPR response to A1 is itself seed-dependent — see §25.6).

### 25.6 XGBoost's FPR response to A1 is seed-dependent (5 seeds is too few to characterize it)

Building the demo (`docs/DEMO.md`) surfaced a finding that the archived Phase 0 runs already contained but
the mean-over-seeds tables did not show. Per-seed fixed-threshold FPR at ratio 0.5, CICIDS, rounds
2/4/6/8/10/12/15/20:

| model | seed | r2 | r4 | r6 | r8 | r10 | r12 | r15 | r20 |
|---|---|---|---|---|---|---|---|---|---|
| xgboost | 1 | 0.005 | 0.005 | 0.004 | 0.006 | 0.006 | 0.006 | 0.007 | 0.019 |
| xgboost | 2 | 0.016 | 0.503 | 0.737 | 0.782 | 0.823 | 0.878 | 0.924 | 0.955 |
| xgboost | 3 | 0.006 | 0.007 | 0.053 | 0.538 | 0.693 | 0.714 | 0.734 | 0.800 |
| xgboost | 4 | 0.046 | 0.707 | 0.776 | 0.839 | 0.908 | 0.949 | 0.948 | 0.958 |
| xgboost | 5 | 0.005 | 0.004 | 0.004 | 0.006 | 0.007 | 0.008 | 0.010 | 0.117 |
| rf | 1 | 0.048 | 0.232 | 0.618 | 0.721 | 0.767 | 0.804 | 0.858 | 0.911 |
| rf | 2 | 0.032 | 0.153 | 0.503 | 0.700 | 0.735 | 0.776 | 0.840 | 0.894 |
| rf | 3 | 0.021 | 0.088 | 0.362 | 0.612 | 0.706 | 0.743 | 0.776 | 0.853 |
| rf | 4 | 0.015 | 0.095 | 0.383 | 0.615 | 0.728 | 0.740 | 0.788 | 0.869 |
| rf | 5 | 0.042 | 0.284 | 0.647 | 0.729 | 0.779 | 0.836 | 0.880 | 0.917 |

XGBoost is bimodal: seeds 2 and 4 reach 70-84% FPR by round 8-10; seeds 1 and 5 stay below 2% through round
10 and only seed 5 climbs at all by round 20 (to 12%); seed 3 sits in between, jumping late (round 6-8). RF
climbs on all 5 seeds, with no seed staying flat. The mean-over-seeds tables used everywhere else in §21-25
hide this: the XGBoost mean at round 10 is dragged up by two seeds while three show no effect at all, which
is a bimodal outcome, not a noisy estimate of one common trajectory. **5 seeds is too few to characterize
XGBoost's response to A1 under the fixed threshold; report the per-seed trajectories alongside the mean, not
mean +/- std alone, until more seeds are run.** RF's channel does not show this problem here. The live demo
(`docs/DEMO.md`) uses RF for this reason: a demo needs the effect to reproduce on every run, and only RF does.

### 25.7 Parked: session-level D1 (future work)

Not run. Reasons: (a) any session-level D1 would have to beat ShareCap (§25.3), which already recovers ~100%
at both ratios and retains 0.74-0.83 on CICIDS, so the headroom is small; (b) the dataset that carries source
IPs and timestamps (GeneratedLabelledFlows) is form-gated and unavailable. The per-flow diagnostic in §25.4
motivates the idea but does not test it. **No experiments follow the cap curve (§25.5).**


## 26. F3/F4 predated the honest calibration — re-run under tau=0.1, §17 refined

§17's damage-vs-distance table and trajectory figures were built under the old, miscalibrated
round-0 threshold (control FPR 0.046 RF / 0.039 XGBoost against a 0.01 target). §19.1's fix
moved the honest control to 0.007 and the FPR-channel onset from ~1-2% to ~10-20% poison
(§23), but the paper's own F3/F4 figures were never rebuilt against that fix — they were still
reading `results/phase0/loop/cicids/` (old calibration). This is the one exception to §25.7's
"no experiments follow the cap curve": not new research, a figure-correctness fix.

**Re-run** (`results/phase0/loop/cicids_recal/`, tau=0.1): scenarios `{control, a1}`, ratios
`{0.05, 0.1, 0.2, 0.5}`, jitter `{0, 0.01, 0.03, 0.1, 0.3, 0.7, 1.5}`, 5 seeds, RF (25 trees,
depth<=16) + XGBoost (60 trees), both threshold modes, 4 workers. 170 of 290 jobs were new (120
already existed from earlier sweeps at overlapping grid points); 34.8 minutes wall clock.

**What changed from §17's numbers.** The cliff location is unchanged (realized NN ~0.011 vs
~0.014, the same factor-of-~1.3 gap §17 reported), and it is sharper than §17 showed, not
different in kind. Fixed-threshold FPR increase at jitter 0 (raw benign fidelity), paired
same-seed delta, final round:

| ratio | RF | XGBoost |
|---:|---:|---:|
| 0.05 | +0.009 | +0.005 |
| 0.10 | +0.025 | +0.014 |
| 0.20 | +0.337 | +0.279 |
| 0.50 | +0.880 | +0.563 |

These match §21.1's spot values at the same ratios (RF +0.337/+0.880 at 20%/50%) to three
decimal places — §21.1's numbers were already tau=0.1; this re-run adds the full jitter grid
around them, which did not exist as a paper figure before.

**What is refined, not overturned.** §17 point 4 described a "flat, distance-independent"
RF sub-cliff FPR residual of +0.02 to +0.056 from realized 0.014 to 1.06, origin not
established. Under tau=0.1 that residual is smaller and mostly inside the noise floor
(2 sigma_control = 0.009 at ratio 0.5): every jitter from 0.01 to 0.10 sits at +0.001 to
+0.006 (RF) — clearly inside noise — and only the two largest jitters at the two largest
ratios edge past it (ratio 0.2/jitter 0.7: +0.011; ratio 0.5/jitter 0.7: +0.012). The old
calibration's inflated control variance was hiding how small this residual actually is; it has
not vanished but it is no longer the "flat +0.02 to +0.056" effect §17 described, and whatever
residual remains is concentrated at high ratio and high jitter rather than flat across the
whole distance range. XGBoost shows no comparable residual (values scatter slightly negative
throughout, consistent with §23's "no TPR/FPR channel beyond the cliff").

The recalibrated-threshold TPR channel (§23's RF-only, works-at-distance finding) is confirmed
across the full grid, not just the two spot jitters §23 reported: RF's delta\_tpr at ratio 0.2
is -0.140 (raw) -> -0.053 -> -0.012 -> -0.051 -> -0.074 -> -0.109 -> -0.103 as jitter rises
0 -> 0.01 -> 0.03 -> 0.1 -> 0.3 -> 0.7 -> 1.5: damage dips near the cliff and rises again at
distance, the U-shape §23 described as "saturating near -0.10 from 20%", now visible at every
grid point rather than inferred from two. XGBoost's TPR delta at the same ratio stays within
roughly +/-0.08 with no consistent sign, confirming "no TPR channel" rather than a small one
in the same direction as RF's.

**Figures.** F3 (`paper/figures/F3_damage_vs_fidelity.pdf`) and F4
(`paper/figures/F4_a1_trajectory.pdf`) are regenerated from this data
(`experiments/paper_figures.py:fig_f3/fig_f4`, source `_load_recal`/`_paired_damage_recal`). F3
drops the dotted S0 reference line that the old-calibration figure carried: this re-run did not
include an S0 arm (S0's own tau=0.1 CICIDS numbers are a class-prior reference only, §17 point
5, not re-run here), and overlaying an old-calibration S0 line on a tau=0.1 FPR/TPR plot would
mix calibrations in one figure.

### 26.1 Confirming the RF TPR channel: paired t at every jitter, both ratios

§23's headline recalibrated-threshold number (RF, ratio 0.2, realized NN ~0.56: -0.109 +/-
0.038) was two spot values. The full re-run (s26) confirms it and extends it across the whole
jitter grid, with the paired t-statistic at each point (5 seeds, `delta = tpr_a1 - tpr_control`
at matching seed, final round):

| model | ratio | jitter | realized NN | mean delta_tpr | sd | t |
|---|---:|---:|---:|---:|---:|---:|
| rf | 0.2 | 0.00 | 0.011 | -0.140 | 0.015 | -20.3 |
| rf | 0.2 | 0.01 | 0.014 | -0.053 | 0.079 | -1.5 |
| rf | 0.2 | 0.03 | 0.031 | -0.012 | 0.058 | -0.5 |
| rf | 0.2 | 0.10 | 0.091 | -0.051 | 0.098 | -1.2 |
| rf | 0.2 | 0.30 | 0.254 | -0.074 | 0.045 | -3.6 |
| rf | 0.2 | 0.70 | 0.559 | **-0.109** | 0.038 | **-6.3** |
| rf | 0.2 | 1.50 | 1.056 | -0.103 | 0.038 | -6.0 |
| rf | 0.5 | 0.00 | 0.011 | -0.282 | 0.038 | -16.6 |
| rf | 0.5 | 0.01 | 0.014 | +0.010 | 0.042 | +0.5 |
| rf | 0.5 | 0.03 | 0.031 | +0.011 | 0.021 | +1.2 |
| rf | 0.5 | 0.10 | 0.090 | +0.015 | 0.025 | +1.3 |
| rf | 0.5 | 0.30 | 0.254 | -0.016 | 0.022 | -1.6 |
| rf | 0.5 | 0.70 | 0.559 | -0.119 | 0.082 | -3.2 |
| rf | 0.5 | 1.50 | 1.058 | -0.095 | 0.031 | -6.9 |
| xgboost | 0.2 | 0.00 | 0.011 | -0.060 | 0.052 | -2.6 |
| xgboost | 0.2 | 0.01 | 0.014 | +0.073 | 0.023 | +7.1 |
| xgboost | 0.2 | 0.03 | 0.031 | +0.077 | 0.023 | +7.4 |
| xgboost | 0.2 | 0.10 | 0.091 | +0.042 | 0.024 | +4.0 |
| xgboost | 0.2 | 0.30 | 0.254 | +0.041 | 0.016 | +5.9 |
| xgboost | 0.2 | 0.70 | 0.559 | +0.017 | 0.026 | +1.5 |
| xgboost | 0.2 | 1.50 | 1.058 | -0.007 | 0.012 | -1.3 |
| xgboost | 0.5 | 0.00 | 0.011 | -0.219 | 0.058 | -8.5 |
| xgboost | 0.5 | 0.01 | 0.014 | +0.005 | 0.029 | +0.4 |
| xgboost | 0.5 | 0.03 | 0.031 | -0.003 | 0.042 | -0.2 |
| xgboost | 0.5 | 0.10 | 0.090 | +0.027 | 0.033 | +1.9 |
| xgboost | 0.5 | 0.30 | 0.254 | +0.012 | 0.034 | +0.8 |
| xgboost | 0.5 | 0.70 | 0.559 | -0.001 | 0.022 | -0.1 |
| xgboost | 0.5 | 1.50 | 1.058 | +0.003 | 0.006 | +0.9 |

**Confirmed, with a refinement to how it should be described.** RF's TPR channel at distance is
real: it is significant (|t| > 3) at realized >= 0.25 at both ratios (jitter 0.30/0.70/1.50 at
ratio 0.2; 0.70/1.50 at ratio 0.5), always in the damaging direction, and the §23 headline point
(ratio 0.2, jitter 0.70, t = -6.3) holds exactly. But it is not a clean monotone function of
distance: the mid-range (jitter 0.01-0.10, realized 0.014-0.10) is not individually significant
at either ratio (|t| < 1.6) — a real dip, not just "gone", between the cliff and where the
far-distance effect resumes. "Present at every distance tested" (s23, and this paper's s6)
should be read as "present at the near and far ends of the grid, with a statistically
indistinguishable-from-zero dip in the middle," not as a flat effect across the whole range.

**XGBoost does not have a comparable channel, but the mid-grid fluctuations are themselves
significant** — just not in the damaging direction. At ratio 0.2, jitter 0.01/0.03/0.10/0.30 all
clear |t| > 3, but every one of them is *positive* (TPR improves under poisoning at those
settings, t up to +7.4): whatever is happening there is not an attack effect, and it does not
repeat at ratio 0.5 (same jitters: |t| < 2, mixed sign). Reading XGBoost's row as "noise" is
imprecise; the honest statement is "no channel in the damaging direction, though the model's
TPR is not perfectly stable under poisoning either" -- s6 is corrected to say this.

**Erratum to the two paragraphs above: the significance calls do not survive correction for
multiple comparisons.** The 28 tests in the table (later extended to 36 with the two jitters
added in s26.2) are one family -- the claim under test is "does A1 damage the TPR channel
anywhere on this grid" -- and reading off which individual cells clear an uncorrected p < 0.05
inflates the false-positive rate across 28-36 simultaneous tests well past 5%. Holm-Bonferroni
step-down correction (family-wise alpha = 0.05, ranked by p-value, `p_(k) < 0.05 / (m - k + 1)`)
applied to all 36 (model x ratio x jitter) cells for delta_tpr:

| rank | model | ratio | jitter | mean delta_tpr | t | p | Holm threshold | survives |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | rf | 0.2 | 0.000 | -0.140 | -20.32 | 0.00003 | 0.00139 | **yes** |
| 2 | rf | 0.5 | 0.000 | -0.282 | -16.57 | 0.00008 | 0.00143 | **yes** |
| 3 | xgboost | 0.5 | 0.000 | -0.219 | -8.49 | 0.00105 | 0.00147 | **yes** |
| 4 | xgboost | 0.2 | 0.030 | +0.077 | +7.35 | 0.00182 | 0.00152 | no |
| 5 | xgboost | 0.2 | 0.010 | +0.073 | +7.15 | 0.00203 | 0.00156 | no |
| 6 | rf | 0.5 | 1.500 | -0.095 | -6.95 | 0.00225 | 0.00161 | no |
| 7 | rf | 0.2 | 0.700 | -0.109 | -6.34 | 0.00316 | 0.00167 | no |
| 8 | rf | 0.2 | 1.500 | -0.103 | -6.02 | 0.00382 | 0.00172 | no |
| ... | | | | (28 more, all p >= 0.004, all fail) | | | | no |

**Only three of 36 cells survive: RF at both ratios and XGBoost at ratio 0.5, all at jitter 0
(raw copy fidelity).** Nothing at the far end of the grid survives -- not rank 6, 7, or 8 above,
not any jitter >= 0.3 at either ratio for either model. The pre-registered bar set for this
correction (agreed before running it: the far-end claim stands only if it holds at both ratios
and at least two adjacent jitters, after correction) is not met. **"Works at every distance
tested" and "present at the near and far ends of the grid" (both stated above, and in s6) are
withdrawn.** What is left, at the correction level this family of tests supports: a robust TPR
effect at raw copy fidelity, for RF at both ratios and XGBoost at one of two ratios tested (not
at ratio 0.2 -- XGBoost's own jitter-0 cell, t = -2.58, p = 0.061, does not clear even its own
uncorrected threshold). The apparent recovery at large jitter in RF's raw means (Figure 3,
right column) is visually real and reproduces at both ratios, but this correction cannot
distinguish it from chance given the number of comparisons made; it is reported as an
**observed, unconfirmed pattern**, not a second established channel. No mechanism for it is
proposed.

**A separate, smaller family is not affected by this.** Section 6's mechanism-isolation result
(a1 vs. a1truth vs. s0j vs. junk, one fixed jitter, ratio 0.2, Figure 5) tests four arms against
each other under a design that holds jitter fixed and varies only what the poison *is* -- a
family of 4 comparisons, not 36, and even a Bonferroni correction within that family of 4
(threshold 0.0125) is cleared by a1's t = -6.3, p = 0.0032. That result stands on its own terms.
It happens to use the same underlying (rf, ratio 0.2, jitter 0.7) cell that fails the 36-test
correction above -- the same t-statistic is significant or not depending on which family of
tests it is judged against, which is not a contradiction, it is what multiple-comparison
correction means: the mechanism-isolation section asked one pre-specified question at one
distance, and this section swept a whole grid.

### 26.2 Locating the cliff finer: the median x-axis cannot resolve it; p5 can

Optional follow-up to s26: two finer jitter settings (0.002, 0.005), ratios 0.2 and 0.5, RF and
XGBoost, fixed threshold, to place the cliff's location more precisely between realized 0.011
(raw) and 0.014 (jitter 0.01). It does not sit in between.

| model | ratio | jitter | realized median | realized p5 | delta_fpr |
|---|---:|---:|---:|---:|---:|
| rf | 0.2 | 0.000 | 0.0111 | 0.0010 | +0.337 |
| rf | 0.2 | 0.002 | 0.0112 | 0.0021 | +0.003 |
| rf | 0.2 | 0.005 | 0.0119 | -- | +0.003 |
| rf | 0.2 | 0.010 | 0.0144 | 0.0079 | +0.004 |
| rf | 0.5 | 0.000 | 0.0108 | -- | +0.880 |
| rf | 0.5 | 0.002 | 0.0110 | -- | +0.004 |
| rf | 0.5 | 0.005 | 0.0117 | -- | +0.003 |
| xgboost | 0.2 | 0.000 | 0.0111 | -- | +0.279 |
| xgboost | 0.2 | 0.002 | 0.0112 | -- | -0.004 |

**The median barely moves (0.0108-0.0119 across jitter 0-0.01) while the damage collapses
entirely between jitter 0 and jitter 0.002** -- RF ratio 0.2 goes from +0.337 to +0.003, inside
the noise floor, at a jitter so small the median realized distance changes by about 1%.
Jitter 0's 5th-percentile realized distance is 0.0010; jitter 0.002's is already 0.0021 --
roughly doubled. **The median (this paper's x-axis for every A1 figure) is the wrong ruler for
where the cliff sits; the lower-tail p5 is the one that moves when the damage does.** This is
consistent with, and sharpens, s17's original observation ("the cliff is the removal of the
lower tail of near-exact twins") -- it is not simply consistent with it, it shows the median
plot (Figure 3, `paper/figures/F3_damage_vs_fidelity.pdf`) *cannot* resolve the cliff's location
at all: on a median-distance x-axis, jitter 0/0.002/0.005 all but coincide, yet two of those
three points show catastrophic damage and one does not. F3 is regenerated with these two points
included (ratios 0.2 and 0.5 only, since that is what was run) precisely so this is visible
rather than papered over by the x-axis choice. A p5-based x-axis was not substituted for the
median one already used everywhere else in this paper's tables and prior sections; doing so
would require re-deriving every earlier cliff statement, which is out of scope for an optional
follow-up. The honest statement is: **the median distance at which A1's FPR damage disappears
is not a well-defined quantity from this data** -- damage disappears within a jitter step whose
median barely moves, so "the cliff sits at realized 0.011-0.014" (s17, s26) should be read as
"the cliff sits within the resolution of the median statistic," not as two comparable points on
a continuous curve.

### 26.3 Twin fraction: a tail statistic that resolves the cliff, and the exact-duplicate count

s26.2 showed the median realized distance cannot resolve where the FPR cliff sits -- it moves by
about 1% across the exact jitter range (0 to 0.002) where the damage collapses. This defines and
measures a tail statistic that can, and answers the follow-up question of whether the near-jitter
damage is driven by literal exact duplicates of production benign traffic or by close-but-not-
identical near-twins.

**Twin fraction** is the share of a poison batch's rows whose nearest trusted_eval benign
neighbour (in normalized feature space, same RMS metric as the existing `FidelityMeter` guard-(c)
check) is within `delta` of that neighbour. `delta = 0.0015` is the midpoint of jitter 0's p5
(0.00093, s26.2) and jitter 0.002's p5 (0.00206, s26.2) -- the boundary of the regime change s26.2
located, chosen from the data rather than an arbitrary round number. Computed once by
`experiments/phase0_twin_fraction.py` over the full CICIDS honeypot pool (n=344,221 rows) at each
jitter in the damage-vs-distance grid, committed to
`results/phase0/cicids/twin_fraction_by_jitter.csv`:

| jitter | median | p5 | twin fraction |
|---:|---:|---:|---:|
| 0.000 | 0.01068 | 0.00093 | **0.1053** |
| 0.002 | 0.01083 | 0.00205 | 0.00345 |
| 0.005 | 0.01159 | 0.00433 | 0.0 |
| 0.010 | 0.01409 | 0.00798 | 0.0 |
| 0.030 | 0.03099 | 0.02156 | 0.0 |
| 0.100 | 0.09028 | 0.06554 | 0.0 |
| 0.300 | 0.25368 | 0.18564 | 0.0 |
| 0.700 | 0.55832 | 0.41116 | 0.0 |
| 1.500 | 1.05490 | 0.77098 | 0.0 |

**Twin fraction is a near-step function, and it lines up with where the FPR damage disappears.**
At jitter 0 (raw copies of pool benign rows, no perturbation), 10.5% of the poison batch has a
trusted-eval benign row within 0.0015 RMS distance -- these rows sit inside the tolerance a
fixed-threshold detector cannot distinguish from a real user. By jitter 0.002 that has fallen to
0.35%, and by jitter 0.005 it is exactly zero for the rest of the grid tested. This is the same
collapse s26.2 located by the FPR numbers (RF ratio 0.2: delta_fpr +0.337 at jitter 0, +0.003 at
jitter 0.002) but now stated as a property of the poison batch itself, independent of any
downstream retraining run. Median distance cannot see this at all (0.0107 to 0.0108 across the
same two jitters); twin fraction moves by 30x.

**Exact-duplicate count: zero.** `assert_disjoint_from_eval` (already run at partition-build time
to guarantee `trusted_eval` is untouched by the loop) was re-run here on the loop's own
`pool_benign`/`trusted_eval` arrays and confirms no row in the honeypot pool is a float32
content-identical duplicate of any trusted_eval benign row, at any jitter including 0. **The
jitter-0 damage is therefore driven by near-duplicates within 0.0015 RMS distance, not literal
copies.** This distinction matters for how the mechanism is described: the attacker does not need
to replay byte-identical captured flows (which would require having recorded a real user's
session); replaying pool-derived benign feature vectors with no added jitter already lands 10.5%
of the batch inside the twin-fraction tolerance, because CICIDS2017's benign traffic is itself
highly self-similar (s5, s16) -- many benign flows are near-duplicates of each other before any
adversary touches the data. The channel needs the attacker to reproduce production-like benign
*feature statistics* at high fidelity, not to exfiltrate specific victims' traffic; CICIDS makes
that easy only because its benign class already sits in a narrow, repetitive region of feature
space, which is a property of this dataset's generation process, not a general property of
production network traffic. Whether real production benign traffic is similarly self-similar
(and thus similarly exploitable) is untested and stated as a limitation, not assumed.

**Consequence for the paper's capability axis and F3.** Median realized distance is dropped as
the load-bearing x-axis for the fidelity/damage relationship; twin fraction (delta=0.0015,
defined above) replaces it as the primary capability-axis statistic in Section 3 and the primary
x-axis of Figure 3. Median distance is kept as a secondary/appendix figure, since it is still the
right statistic for the far end of the grid where twin fraction is uniformly zero and cannot
distinguish jitter 0.03 from jitter 1.5.

### 26.5 Erratum to s23 ("two channels", "RF-only"): superseded by s26.1's Holm correction

s23's "two channels" table and its "TPR channel is RF-only" finding predate the s26.1
Holm-Bonferroni correction and read differently once the full 36-cell grid is corrected for
multiple comparisons. This does not change s23's null-control result (prior shift and volume
alone are null, label conflict is the mechanism -- that stands); it changes how the *surface* of
the damage is described.

**"Two channels" is retired.** There is one mechanism (label conflict) and one requirement
(near-duplicate mimicry fidelity, s26.3's twin fraction). The threshold policy in force decides
which metric shows the damage, not whether damage occurs: a fixed threshold takes it as a false
positive, a recalibrated one takes it as lost detection (TPR). These were described as two
separate "channels" in s23; they are one effect read through two measurement instruments.
Recalibrating does not remove the damage, it relocates where it shows up -- s26.1's TPR numbers
and s17/s26's FPR numbers are the same underlying rows, scored two ways.

**"TPR channel is RF-only" does not survive s26.1's correction.** s23 read XGBoost as having "no
TPR channel" from an uncorrected, single-cell comparison. s26.1's Holm-corrected table has
XGBoost surviving at ratio 0.5, jitter 0 (t=-8.49, p=0.00105, rank 3 of 36) -- copy-level
fidelity, the same regime as RF. XGBoost's own ratio-0.2, jitter-0 cell does not survive
(t=-2.58, p=0.061), so the corrected statement is "confirmed for XGBoost at one of two poison
ratios tested," not "none," and not "RF-only."

**Figure 5's single-distance result needs to be read against both families it belongs to.** The
mechanism-isolation bar (RF, recalibrated TPR, ratio 0.2, jitter 0.7, t=-6.3, p=0.0032, s23) is a
pre-specified test in its own 4-arm family and clears even a Bonferroni threshold within that
family (0.0125, s26.1). It is also cell (rf, 0.2, jitter=0.7) in the 36-cell grid family, where it
does not survive Holm correction (rank 7 of 36, t=-6.34, p=0.00316, Holm threshold 0.00167,
s26.1). Both statements are correct at once, for the same t-statistic, because they answer
different questions under different correction: "does the conflict matter at this one
pre-registered distance" (yes) versus "does damage at this distance generalise across a 36-point
grid without inflating the false-positive rate of the test itself" (not confirmed). Five seeds is
low power for either family; report the pre-specified result as **an effect found, not yet shown
to generalise**, not as absent. s26.4 (if run) is the attempt to settle whether it generalises
with more seeds and a smaller, pre-registered family at the same distances.

**What changes in the paper:** drop "two channels, RF-only TPR channel, works at every distance"
everywhere it appears (Table 2, s3's capability axis prose, s6, PAPER_PLAN.md's claim paragraph
and contributions). Replace with: one mechanism, one requirement (twin fraction), surfaced as FPR
under a fixed threshold or TPR loss under recalibration, confirmed at copy-level fidelity for both
models (RF at both ratios tested, XGBoost at one of two), with a separate pre-specified
single-distance result (RF, jitter 0.7) reported honestly as an effect not yet confirmed to
generalise across the grid.

### 26.6 Pre-registration: does RF's at-distance TPR pattern generalise? (written before running)

s26.1/s26.5 report RF's apparent TPR recovery at large jitter as an observed, unconfirmed
pattern -- real in the raw 5-seed means, reproducing at both ratios, but not separable from
chance once the 36-cell grid sweep is corrected for multiple comparisons. This pre-registers a
smaller, targeted family to test it properly with more seeds, **written and committed before the
run**, per this project's convention that a correction's pass/fail bar is fixed in advance.

**Family:** RF, recalibrated-threshold TPR only, jitter $\in \{0.3, 0.7, 1.5\}$ x poison ratio
$\in \{0.2, 0.5\}$ = 6 cells. Holm-Bonferroni step-down, family-wise $\alpha = 0.05$, within this
family of 6 only (not re-merged into the 36-cell family from s26.1).

**Seeds:** 15 total -- the existing 5 (seeds 0-4) plus 10 new (seeds 5-14), same paired-t design
as s26.1 (A1 vs. same-seed control, final round).

**Confirmation bar, fixed now:** the at-distance pattern is **confirmed** if and only if at least
2 adjacent jitters (of the 3 tested: 0.3, 0.7, 1.5) survive Holm correction **at both ratios**.
Anything short of that (fewer than 2 adjacent jitters, or confirmed at only one ratio) is
**not confirmed**, and is reported as such -- not reframed as a weaker positive result.

**What does not change regardless of outcome:** this is a follow-up characterisation of a
pattern already labelled unconfirmed; §1-§9 of the paper are drafted assuming "unconfirmed" and
are not blocked on this result. If it confirms, one sentence in §6 and Table 2 is updated to
say so, with the new cell count and seeds noted. If it does not confirm, s26.1/s26.5's existing
language stands unchanged and this section records the negative result for the record.

Run: `experiments/phase0_loop.py --dataset cicids --val-nn-tau 0.1 --scenarios control a1 --models rf --jitters 0.3 0.7 1.5 --ratios 0.2 0.5 --seeds 15 --workers 4 --out results/phase0/loop/cicids_recal --no-fidelity` (job CSVs already present for seeds 0-4 at these cells are skipped by the existing resume-by-file logic; this run only adds seeds 5-14).
