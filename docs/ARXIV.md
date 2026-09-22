# arXiv submission metadata (prepared, not submitted)

This is prep only — nothing here has been submitted. Fill in the TBDs and submit yourself.

## Title

Poisoning the Deception Loop: Label Conflict in Honeypot-Fed Intrusion Detection

(Working alternate, if preferred: "When the Honeypot Writes the Labels: Poisoning Self-Training
Intrusion Detectors" — see `paper/main.tex`'s title comment.)

## Author / affiliation

`paper/main.tex` still has placeholder values (`Author One`, institution/city/country/email all
`TBD`) — these were never filled in during drafting because they're your identity to supply, not
something to infer or invent. Before submitting, fill in:
- Author name(s), in the order they should appear
- Affiliation (institution, city, country)
- Contact email
- The venue line (`\acmConference[AISec '26]{...}{TBD}{TBD}`) can stay as a preprint-only
  placeholder or be removed entirely for an arXiv-only preprint — ACM's own guidance is that a
  preprint should not claim ACM's conference formatting metadata (ISBN/DOI) until accepted, so
  the `\acmISBN{TBD}` / `\acmDOI{TBD}` lines should either stay `TBD` or be deleted for the arXiv
  version, not filled with placeholder-looking real-format values.

## Abstract (plain text, no LaTeX macros)

Checked by hand that this reads correctly with every `\%`, `--`, and `\emph` etc. resolved to
plain characters — this is what should go in arXiv's abstract field, not the `.tex` source.

> Honeypot-fed intrusion detectors retrain on decoy traffic auto-labeled malicious by policy, on
> the argument that anything a decoy sees is unsolicited and therefore free ground truth. That
> argument assumes the label is trustworthy because the source is a decoy; it is not, because the
> labelling policy is public and the attacker chooses exactly what the decoy sees. We characterise
> the resulting attack on a modern, flow-based retraining loop: one mechanism, a label that
> contradicts its neighbourhood, that a fixed detection threshold surfaces as false positives and
> a recalibrated one surfaces as lost detection, not two independent effects. The false-positive
> form needs near-duplicate mimicry fidelity and at least 10-20% of the training set poisoned, in
> both models we evaluate, after Holm-Bonferroni correction across the full grid we test. The
> detection-loss form needs that same fidelity in both models, but for one of them, random forest,
> we further confirm with a dedicated, higher-powered follow-up that it also holds across a wide
> range of lower mimicry fidelity, not only at copy-level fidelity -- an effect a first, larger and
> lower-powered test could not resolve and that we report as confirmed once a properly targeted
> test could. A generic label-consistency defense fails structurally, because the poison agrees
> with the defender's own labelling policy; the cost-of-influence defense we set out to propose
> does not beat a matched no-skill baseline, a negative result we report rather than paper over.
> A one-line cap on the honeypot's effective training-set share is undominated by every
> alternative we test and costs almost nothing to run. We additionally measure that CICIDS2017's
> benign traffic is narrow enough that an attacker reaches damaging fidelity largely for free,
> which bounds what this widely used benchmark can demonstrate about the attack's cost in general.

Word count: ~220 words, well inside arXiv's practical abstract length.

## Categories

- **Primary: cs.CR** (Cryptography and Security). This is a security paper about a specific
  attack and defense on an intrusion detection system; cs.CR is where a reader looking for
  poisoning attacks, IDS security, or honeypot-adjacent threat models would search first, and
  where the paper's own related work (Barreno et al., Biggio & Roli, the RAID/S&P/IMC lineage in
  Section 2) is catalogued.
- **Secondary: cs.LG** (Machine Learning). The mechanism is a training-data poisoning attack
  against two standard supervised classifiers (random forest, XGBoost) and the defenses are
  sample-reweighting/label-sanitization methods — squarely ML-adjacent, and cs.LG is the
  secondary category most poisoning-attack papers in this space (Biggio, Rubinstein, Kloft &
  Laskov, all cited) carry alongside cs.CR.

No other secondary category is a strong fit: the paper doesn't contribute new network-measurement
methodology (cs.NI) or a new dataset-critique methodology beyond a single measurement used in
service of the main argument (which would be a stretch to justify as a third category on its
own).

## License

**Recommend: CC BY 4.0.**

Why: arXiv's default recommendation for papers without a specific publisher requirement is CC BY
4.0 or CC BY-NC-SA; since this is a preprint with no venue commitment yet (Section "Author /
affiliation" above), CC BY 4.0 keeps the most options open — it permits any downstream reuse
(including commercial) with attribution, which is what most CS conference/workshop venues
(including ACM's own policies for accepted papers) are compatible with layering on top of later.
A more restrictive license (CC BY-NC-SA, or arXiv's default non-exclusive license) would need to
be reconciled with whatever the eventual venue requires for the camera-ready version, and some
venues (including ACM, per its author rights policy) are more straightforward to satisfy when the
preprint is already maximally permissive. If AISec or wherever this ends up has a specific
license requirement for accepted-paper preprints, that should override this recommendation at
that point — this is a starting choice for the arXiv-only preprint stage, not a permanent one.

## Not included here

- Comments/description field for the arXiv listing (e.g., page count, "N pages, M figures") —
  trivial to fill in at submission time from the compiled PDF, not drafted here since it depends
  on whatever the final page count is when you actually submit.
- ACM CCS concepts / keywords (`\keywords`, `\ccsdesc`) — `paper/main.tex` doesn't currently set
  these; they're an ACM-format nicety, not part of arXiv's own metadata, and can be added
  independently if/when targeting the ACM camera-ready.
