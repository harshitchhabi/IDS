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
