# arXiv submission metadata (prepared, not submitted)

This is prep only — nothing here has been submitted. Submission package: `arxiv_submission.zip`
at the repo root (rebuild with `main.tex` from `arxiv_pkg_build/`, `main.bbl` inlined so the
package compiles standalone without `references.bib`).

## Title

Poisoning the Deception Loop: Label Conflict in Honeypot-Fed Intrusion Detection

(Working alternate, if preferred: "When the Honeypot Writes the Labels: Poisoning Self-Training
Intrusion Detectors" — see `paper/main.tex`'s title comment.)

## Author / affiliation

`paper/main.tex` has: **Harshit Chhabi, Vellore Institute of Technology, Vellore, India**,
email `harshitchhabi@gmail.com`. City is VIT's main campus — check that's the right campus to
list if that matters to you (VIT also has Chennai, Bhopal and AP campuses). The build uses the
`nonacm` class option, so there is no conference line, ISBN, or DOI to fill in — ACM's own
guidance is that a preprint should not claim ACM's conference formatting metadata until accepted,
and `nonacm` suppresses that block entirely rather than showing placeholder values.

## Abstract (plain text, no LaTeX macros)

Checked by hand that this reads correctly with every `\%`, `--`, and `\emph` etc. resolved to
plain characters — this is what should go in arXiv's abstract field, not the `.tex` source.

> Honeypot-fed intrusion detectors retrain on decoy traffic auto-labelled malicious, on the
> argument that anything a decoy sees is unsolicited and therefore free ground truth. That label
> is only trustworthy if the attacker cannot predict the labelling policy; when it can, it chooses
> what the decoy sees. We characterise the resulting attack on a flow-based retraining loop. One
> mechanism, a label that contradicts its neighbourhood, shows up as false positives under a fixed
> detection threshold and as lost detection under a recalibrated one. The false-positive form needs
> near-duplicate mimicry fidelity and 10-20% of the training set poisoned; for random forest, a
> higher-powered follow-up confirms that the detection loss also holds at much lower fidelity. A
> generic label-consistency defense fails because the poison agrees with the defender's own
> labelling policy, and the cost-of-influence defense we set out to propose does not beat a
> no-skill baseline. A one-line cap on the honeypot's effective share of the training set is
> Pareto-undominated over the configurations we test and costs almost nothing to run; a sliding
> retention window reduces damage, but an attacker can buy it back with more traffic.
> Pre-registered follow-ups show that the copy-fidelity damage, and the benchmark degeneracy behind
> it, carry over to a reprocessed CICIDS2017 release and to UNSW-NB15. The attack also damages
> logistic regression and a small MLP, in different forms. Isolating the label conflict as the sole
> mechanism holds only on CICIDS2017 with random forest. We also measure that CICIDS2017's benign
> traffic is narrow enough for an attacker to reach damaging fidelity cheaply, which limits what
> this benchmark can show about attack cost.

Word count: 263 words, 1,732 characters, well inside arXiv's 1,920-character abstract limit.

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
