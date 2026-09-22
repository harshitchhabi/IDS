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
auto-labelled malicious by policy, as a free source of ground truth. That turns the
honeypot into a write channel the attacker controls. We show the resulting attack
works through one mechanism, label conflict, with two channels: a false-positive
channel that needs the attacker to reproduce benign traffic almost exactly, and a
detection-loss channel (in random forests) that works at any distance we tested.
Label-consistency defenses fail structurally, because the poison agrees with the
defender's own labelling policy. Cost-of-influence weighting, our proposed defense,
does not beat a no-skill baseline; a one-line cap on the honeypot's share of the
training set is undominated by every defense we tested. Along the way we measure that
CICIDS2017 is near-degenerate in flow-feature space, which limits what it can show.

## Contributions
1. Threat model: auto-labelled honeypot data as an attacker-controlled write channel
   into IDS training.
2. The attack characterised: one mechanism, two channels, isolated with matched null
   controls; damage as a function of measured mimicry distance, not a jitter knob.
3. The policy-consistency blind spot: why loss-based and other label-consistency
   defenses recover ~0% here.
4. A defense comparison against a proper no-skill baseline: cost weighting fails to
   beat it; a share cap is undominated and costs essentially nothing.
5. A measurement of CICIDS2017 degeneracy under CICFlowMeter features, and what that
   means for claims made on it.

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
- A1 damage vs mimicry distance: cliff at ~0.011-0.014 for the FPR channel.
- Two channels (§23 table): FPR needs copy fidelity and >=10-20% poison; RF's TPR
  channel works at every distance tested; XGBoost has no TPR channel.
- Mechanism isolation: a1truth, s0j, junk all null.
- Recalibrating trades FPR damage for TPR loss.
- XGBoost FPR channel seed-dependent, reported per seed.
- Source: §17, §19, §22, §23, results/phase0/loop/, results/phase0/mechanism/.
- Figure 3: damage vs realized mimicry distance.
- Figure 4: A1 trajectories, fixed vs recalibrated.
- Figure 5: mechanism isolation bars.
- Table 2: the two channels (from §23).

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
