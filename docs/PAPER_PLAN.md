# Paper plan — Poisoning the Deception Loop

Maps every section of the paper to the DECISIONS.md sections and result files it's
built from, so writing is mostly condensing work that's already done.

Target: an 8-page workshop paper plus appendix (AISec-style). Confirm the venue,
template and page limit before day 4 — the page budgets below assume 8 pages.

## Working title
- Poisoning the Deception Loop: Label Conflict in Honeypot-Fed Intrusion Detection
- When the Honeypot Writes the Labels: Poisoning Self-Training Intrusion Detectors

## The claim, in one paragraph
Honeypot–IDS integrations increasingly retrain the detector on honeypot traffic,
auto-labelled malicious by policy, as a free source of ground truth. Paragraph and
Perdisci et al. showed this attack class on signature generators trained on
honeynet-flagged traffic nearly two decades ago; current honeypot-fed ML retraining
loops reintroduce the same design without evaluating the threat. We characterise the
attack on a modern loop: one mechanism, label conflict, one requirement (near-
duplicate mimicry, quantified as twin fraction: the poison needs to sit within a
tight distance of real benign traffic, and needs >=10-20% poison share). The
threshold policy decides where that damage surfaces, not whether it does:
fixed-threshold detectors take it as false positives, recalibrated ones take it as
lost detection (TPR); recalibrating moves the damage, it does not remove it. After
Holm correction across the full grid, both models show the TPR-loss form of the
damage at copy-level fidelity (RF at both poison ratios tested, XGBoost at one); a
pre-specified single-distance test found an effect further out for RF, but the full
grid sweep does not confirm it generalises past that one distance, at the power five
seeds give it — reported as unconfirmed, not absent. Label-consistency defenses fail
structurally, because the poison agrees with the defender's own labelling policy.
Cost-of-influence weighting, initially our proposed defense, is a measured negative
result: it does not beat a no-skill baseline. A one-line cap on the honeypot's share
of the training set is undominated by every defense we tested. Along the way we
measure that CICIDS2017 is near-degenerate in flow-feature space, which limits what
it can show, and that the FPR channel's damage on this dataset is driven by
near-duplicates of real benign traffic rather than by literal duplicates.

## Contributions
1. Threat model: auto-labelled honeypot data as an attacker-controlled write channel
   into IDS training, characterised (mechanism, requirement, null controls) on a
   modern honeypot-fed retraining loop, the design Paragraph/Perdisci's
   signature-generator attack targeted but that current honeypot+ML systems
   reintroduce unevaluated.
2. The attack characterised: one mechanism (label conflict) that surfaces as either
   FPR or TPR damage depending on the threshold policy in force, not two independent
   channels; damage as a function of measured mimicry fidelity (twin fraction, not a
   jitter knob or an unresolving median distance), held to a pre-registered,
   multiple-comparison-corrected significance bar, with a separate pre-specified
   single-distance result reported honestly as unconfirmed at scale.
3. The policy-consistency blind spot: why loss-based and other label-consistency
   defenses recover ~0% here.
4. A defense comparison against a proper no-skill baseline: cost-of-influence
   weighting (not claimed as a novel contribution — a measured negative result) fails
   to beat it; a share cap is undominated and costs essentially nothing.
5. A measurement of CICIDS2017 degeneracy under CICFlowMeter features, including that
   the FPR channel's damage traces to near-duplicate (not exact-duplicate) benign
   rows, and what that means for claims made on it.

## Sections

### 1. Introduction — 1 page
- Honeypot data as free labels for IDS retraining (cite closed-loop papers).
- The inversion: the defender opens a labelled write channel and calls it ground truth.
- One sentence per result, then the contribution list.
- Source: related-work table, §23, §25.
- Figure 1: the loop diagram with the attacker-controlled segment marked.

### 2. Background and related work — 1 page
- Four paragraphs: honeypot–ML integrations; adaptive/LLM honeypots; poisoning of
  network classifiers; poisoning defenses. Two sentences on IDS dataset critiques.
- End with the gap: nobody treats the honeypot's labels as untrusted.

### 3. Threat model — 0.75 page
- Defender retrains on seed data plus honeypot traffic stamped malicious.
- Attacker can send arbitrary traffic to the decoy, knows the labelling policy,
  cannot touch production training data or the model.
- Goals: raise false positives, or suppress detection.
- Capability axis: mimicry fidelity, measured as realized NN distance to benign.
- Source: CLAUDE.md threat model, §4, §17.

### 4. Methodology — 1.25 pages
- The loop: rounds, retention, budget mode, cold-start retraining (§7, §18).
- Datasets and partitions: four disjoint partitions, (day, family) split, four eval
  arms (§1, §3, §10).
- Leakage guards (§2, §11); burst splitting to appendix (§14).
- Threshold policy: fixed vs recalibrated, twin-free calibration fix (§5, §19.1).
- One weight channel (§6). Seeds, determinism (§8).
- Arms: control, S0, A1, plus null controls a1truth, s0j, junk (§19.2, §23).
- Table 1: partitions and row counts per dataset.

### 5. CICIDS2017 is near-degenerate — 0.75 page
- Every family with >500 eval rows, and benign, sits far below the leakage threshold
  at every dedup grid and with burst splitting.
- Consequence: no learning claim on CICIDS; S0 learning claim made on synthetic.
- The 94% of benign validation rows discarded for an honest threshold (§23).
- Source: §10, §15, §16, nn_by_family.csv, grid_sweep.csv.
- Figure 2: per-family median NN RMS, log axis, 0.25 marked.

### 6. The attack — 1.5 pages
- S0 works: honeypot_only 0.4 -> 0.99 on synthetic.
- A1 damage vs mimicry fidelity (twin fraction, §26.3): a cliff, not a gradient.
- One mechanism, one requirement, surfaced by the threshold policy (§26.1
  Holm-corrected table): fixed threshold shows it as FPR; recalibration shows it as
  TPR loss, in both models tested, at copy-level fidelity (RF both ratios, XGBoost
  ratio 0.5). Recalibrating relocates the damage, it does not remove it.
- Figure 5's pre-specified single-distance test (RF, ratio 0.2, jitter 0.7) found an
  effect and clears its own 4-test family; the 36-test grid sweep does not confirm it
  generalises past that one distance at 5-seed power — state both, call it
  unconfirmed, not absent. (§26.4, if run: whether it now generalises.)
- Mechanism isolation: a1truth, s0j, junk all null.
- XGBoost FPR channel seed-dependent, reported per seed.
- Source: §17, §19, §22, §23, §26.1, §26.3, §26.4, results/phase0/loop/,
  results/phase0/mechanism/, results/phase0/cicids/twin_fraction_by_jitter.csv.
- Figure 3: damage vs twin fraction (cliff) and vs median realized distance (full
  grid), side by side.
- Figure 4: A1 trajectories, fixed vs recalibrated.
- Figure 5: mechanism isolation bars, caption notes the single pre-specified
  distance.
- Table 2: one mechanism, two surfaces (from §26.1).

### 7. Defenses — 1.25 pages
- Policy-consistency blind spot: loss filtering recovers ~0% (§23).
- D1 as pre-registered; missed its own sensitivity criterion (§20, §21.5).
- Frontier vs kNN and no-skill baselines; uniform fails at ratio 0.9 (§24.1).
- ShareCap: undominated in all 87 comparisons; cap curve (§25.3, §25.5).
- Overhead: D1 ~781x cheaper than kNN; ShareCap near zero.
- Counter-moves: padding (§21.6), volume (§21.4).
- Figure 6: recovery vs retention frontier with ShareCap + cap curve.
- Table 3: loss-filter recovery by ratio.
- Table 4: defense comparison — recovery r0.5/r0.9, retention CICIDS/synthetic,
  overhead per round.

### 8. Discussion and limitations — 0.5 page
- When it matters: low-entropy benign traffic (IoT, ICS, automated services).
- Advice: cap the honeypot's share; don't trust label-consistency checks.
- Limitations: offline simulation; flow features only; CICIDS degenerate and synthetic
  has no attacker-cost profile; no timestamps (file-order split, §14 erratum);
  5 seeds, XGBoost seed-dependent; ShareCap cap is model/dataset-dependent; no
  adaptive attacker against ShareCap beyond filling the cap.

### 9. Conclusion — 0.25 page

### Appendix
Day-split robustness (§1); burst splitting (§14); guard (a) grid sweep (§11);
D1 definition and full grid (§20, §24); XGBoost per-seed trajectories; padding
(§21.6); full cap curve (§25.5).

## Figures and tables — status
| # | What | Source | Status |
|---|---|---|---|
| F1 | Loop / threat diagram: seed data + honeypot -> auto-label malicious -> retrain -> IDS guarding production, attacker-controlled segment marked | draw | to make (vector, simple boxes and arrows) |
| F2 | Per-family NN distance, log axis | cicids/nn_by_family.csv | to generate |
| F3 | Damage vs realized mimicry distance | loop/cicids/a1_damage_vs_fidelity.png data | restyle |
| F4 | A1 trajectories, fixed vs recalibrated threshold | loop/cicids/a1_trajectory_r0.2.png data | restyle |
| F5 | Mechanism isolation bars | results/phase0/mechanism/ | to generate |
| F6 | Recovery/retention frontier | frontier/ + §25.5 cap curve | add ShareCap + curve |
| T1 | Partitions | partitions.md | condense |
| T2 | Two channels | §23 | lift |
| T3 | Loss-filter blind spot | §23 | lift |
| T4 | Defense comparison | §24.1, §25.3 | merge |

## Writing rules
- Every number traces to a committed CSV or a DECISIONS section; LaTeX comment with
  the source next to each.
- Do not claim: D1 is effective; ShareCap "beats" others (it's undominated); real
  attackers do this; the cliff location generalises across datasets; any S0 learning
  claim on CICIDS; session-level cost weighting works; the CICIDS split is temporal.

## Open items
- [x] §25.5 cap curve
- [x] XGBoost per-seed note
- [ ] F2, F5 generated
- [ ] F6 updated with ShareCap
- [ ] Venue, template, page limit confirmed
