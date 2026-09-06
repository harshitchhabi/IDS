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

**Chosen design (`within_day_temporal`, the default).** Within each capture day,
sort the benign and attack flow streams separately by timestamp and cut each by
cumulative time fraction:

- benign → `seed_train` (0.30) · `prod_benign` (0.20) · `honeypot_pool` (0.30) · `trusted_eval` (0.20)
- attack → `seed_train` (0.40) · `honeypot_pool` (0.40) · `trusted_eval` (0.20)

A sustained attack campaign therefore appears in all three of seed_train, the
honeypot pool, and trusted_eval — separated only in time, which is exactly the
regime the literature's claim lives in. Temporal ordering is preserved (no row
is evaluated against a contemporaneous training row), so there is no leakage in
the classical sense.

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
  cleaning. Near-duplicates are removed here: any row within `near_dup_grid`
  (default 0.02, a per-feature RMS distance in normalized log-IQR units) of an
  already-kept row of the same label is dropped. The check is radius-based, not
  grid-cell-based — grid-cell rounding lets a near-duplicate pair straddle a
  cell boundary and survive, which is the precise failure this guard exists to
  prevent. A guard that never fires is a guard of unknown worth, so the
  synthetic generator injects fingerprint-tight bursts into every sustained
  attack family and the self-test asserts the guard clears them.
- **(b) Temporal guard band.** Rows within `boundary_buffer_seconds / 2` of an
  internal cut time are dropped, so a burst cannot sit across a cut.
- **(c) Nearest-neighbour distance.** For every trusted_eval row, the distance
  in normalized feature space to its nearest honeypot_pool row of the same
  class. Reported as a percentile distribution per class and per attack family.
  If the 5th percentile falls below `nn_leak_p5_threshold` (0.25) the build
  raises `leak_warning`, the explore script exits non-zero, and the S0
  checkpoint must not be trusted until the cause is understood.

## 3. trusted_eval family reporting is three-way

S0's TPR is broken out by where each trusted_eval attack family appears:

- **seen_both** — in `seed_train` and the adversary pool. The loop may improve
  TPR here; this is the arm the literature's claim is about.
- **seed_only** — in `seed_train`, withheld from the adversary pool. This is
  A4's controlled measurement arm.
- **novel** — in neither. Supervised models are expected at ≈0 TPR; this arm
  bounds what the loop cannot do.

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

The feature scaler (log1p then robust median/IQR standardization) is fit on the
training split only, per round, and persisted with the model; a test asserts it
carries no validation or eval statistics. Every `fit` calls a single
`seed_everything` that seeds Python, NumPy and PyTorch and forces deterministic
kernels (`torch.use_deterministic_algorithms(True)`, cuDNN deterministic,
single-threaded); the autoencoder trains full-batch precisely so it is
bit-reproducible. `determinism.md` shows two identical-seed runs producing
identical predictions.

## 9. Python pinned to 3.12

`.python-version` and the `pyproject` constraint pin CPython 3.12. PyTorch wheel
coverage for 3.14 is incomplete and the autoencoder needs torch; pandas 2.3 on
3.14 + NumPy 2.5 also surfaced a `Timedelta` deprecation-to-error. Pinning now
avoids hitting either mid-build.

## 10. Real CICIDS2017 validation — what the synthetic checkpoint hid

The Phase 0 pipeline was re-run unchanged (`--source cicids`, same configs, same
seeds) against the real CICIDS2017 `MachineLearningCVE` CSVs (~2.83M flows).
Results are in `results/phase0/cicids/`, kept alongside the synthetic results
for the methodology table. Getting there needed a handful of real-data fixes
that the synthetic path never exercised — none change the method:

- **Encoding.** The Web-Attack labels carry a non-ASCII dash; read with
  `encoding_errors="replace"` and folded to `-` in `normalize_label`.
- **The near-duplicate guard had to become global and O(n).** A single
  Wednesday DoS burst is ~230k near-identical rows; a radius neighbour graph
  over that does not fit in memory. Guard (a) now runs once over the whole
  cleaned dataset (so a cross-day near-duplicate pair is also caught) using two
  half-offset grid snaps instead of a radius graph — linear, and the offset
  pass catches the boundary-straddle pairs a single grid rounding misses.
- **Row-content hashing** for the disjointness assertion is vectorized
  (`hash_pandas_object`); the string-join version was unusably slow at millions
  of rows.
- **Guard (c)** subsamples the *query* side of the nearest-neighbour search
  (the honeypot-pool index stays complete, so a real near-duplicate is still
  found).

### What the real data showed

1. **CICIDS2017 flow-statistic features are severely degenerate.** After exact
   deduplication (cleaning already drops 25–34% of each day as exact
   duplicates — the documented "duplicate rows" gotcha), guard (a) removes a
   further ~1.01M rows (~49% of what survived cleaning) as near-duplicates at
   the default grid. Most are BENIGN: real web traffic is highly repetitive in
   24 flow-summary features.

2. **Guard (c) fires `leak_warning` under _both_ partition strategies.** For
   `within_day_temporal` it is a true positive: DoS attack flows are a
   near-degenerate feature-space cluster, so a temporal cut through Wednesday's
   DoS campaign puts near-identical Hulk flows in both `honeypot_pool` and
   `trusted_eval` (attack 5th-pct per-feature RMS = 0.000, 87% of pairs within
   grid distance). For `day_split` — whole different days, different attack
   families — it fires on the **benign** class: a benign flow on Thursday is
   feature-space-identical to a benign flow on Friday, and guard (c) cannot tell
   "the same flow appears twice" from "two different flows have identical
   summary statistics". The guard's benign-class leak test is therefore not
   meaningful for a day-disjoint split and should be read as attack-class only.

3. **`seed_only` — A4's controlled measurement arm — is structurally empty on
   CICIDS2017.** Every attack family runs on exactly one capture day, so no
   family can be present in `seed_train` and `trusted_eval` but withheld from
   the pool. A4 cannot be measured on CICIDS2017 flow data without synthetic
   augmentation or a second dataset.

4. **`tpr_novel` is not a single number — it depends entirely on which family
   is novel.** Under `within_day_temporal` the only genuinely-novel family is
   Heartbleed (7 rows) and supervised `tpr_novel = 0.00` — the opposite of the
   synthetic 0.55, confirming that the synthetic generator made "attack" a
   generically separable region. Under `day_split` the novel families are Bot,
   PortScan and DDoS, and RF's `tpr_novel = 0.90`: volumetric/scan attacks sit
   so far outside the benign region that a classifier trained on *any* attacks
   (Patator) flags them without ever seeing the family. Subtle families
   (Heartbleed, and Bot for XGBoost) are missed. The synthetic number was an
   artifact; the real behaviour is family-dependent and spans 0.0–0.9.

5. **Both threshold modes matter more on real data.** `fixed` vs
   `recalibrated` barely differed on synthetic; on CICIDS2017 the
   seed→trusted-eval calibration transfer error is large (RF `eval_fpr` 0.048
   under `fixed` vs 0.010 under `recalibrated`), validating why the loop must
   report both.

6. **The tabular autoencoder collapses on real benign traffic.** Reconstruction
   error on real CICIDS2017 benign has so heavy a right tail that the
   99th-percentile calibration threshold sits beyond every attack too
   (`val_tpr = 0`, `eval_tpr = 0`, AUROC ≈ 0.6–0.8). It needs either a
   higher operating FPR or a different anomaly score before it earns a place.

### Consequence for the S0 checkpoint

The S0 checkpoint ("the clean loop improves the detector over rounds") cannot be
validated as designed on either dataset yet: the synthetic partition makes it
pass trivially, and the real CICIDS2017 partition leaks (attack degeneracy under
`within_day_temporal`; and the eval set is not genuinely held out at the
feature-representation level). Resolving this is a prerequisite for Phase 0's
checkpoint and is the open question to settle before building the loop —
candidate directions: a dataset with per-flow timestamps and less feature
degeneracy, a coarser poison-ratio regime where memorization is not the
dominant effect, connection-5-tuple-level disjointness rather than
feature-level, or accepting `day_split` with attack-class-only leak checking and
the cross-family-generalization framing.
