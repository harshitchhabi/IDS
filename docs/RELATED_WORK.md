# Related work — verified candidates

24 papers, found via web search, each checked against its DOI/arXiv/publisher page (not taken
from a search snippet alone) before being added here or to `paper/references.bib`. Columns:
title, authors (as listed on the verified page), venue, year, and the URL checked. BibTeX key
in parentheses after the title matches `paper/references.bib`.

A candidate is here only if its metadata was independently confirmed on the paper's own page
(arXiv abstract, DBLP record, publisher DOI page, or — where those were blocked, e.g. some
ACM/IEEE/ScienceDirect pages return 403 to an automated fetch — at least two independent search
result snippets that agree on authors/venue/year). Nothing went in on a single AI-generated
search summary alone.

## A. Honeypot-fed ML / closed-loop retraining

The category our threat model belongs to is thin in the peer-reviewed literature; most
honeypot+ML work goes the *other* direction (ML detecting attacks against the honeypot, or ML
*as* the honeypot), not honeypot data feeding a retrained detector's training set. Of the five
rows below, only the last two actually close the loop we attack — a classifier trained or
retrained on honeypot-derived data and then used for detection. `yugai2024honeypot` and
`abdou2021honeymodels` are adjacent (honeypot-plus-ML systems in the same threat surface) but
do not retrain a detector on honeypot output, so they motivate the category without being
direct instances of the design we evaluate; they are kept here for that reason, not cited in
§1 as retraining systems.

| Title | Authors | Venue | Year | Checked |
|---|---|---|---|---|
| Using Machine Learning Algorithms and Honeypot Systems to Detect Adversarial Attacks on Intrusion Detection Systems (`yugai2024honeypot`) | P. E. Yugai, D. A. Moskvin | Automatic Control and Computer Sciences 58, 1226–1233 | 2024 | link.springer.com/article/10.3103/S014641162470086X |
| HoneyModels: Machine Learning Honeypots (`abdou2021honeymodels`) | Ahmed Abdou, Ryan Sheatsley, Yohan Beugin, Tyler Shipp, Patrick McDaniel | MILCOM 2021 | 2021 | arxiv.org/abs/2202.10309 |
| Creating an Adaptive Defense Architecture Using an Adaptive Honeypot Algorithm and Network Traffic Classifier (`matcheswala2024creating`) | Mohammed Shaad Mehboob Matcheswala, Amir Javed | AI Applications in Cyber Security and Communication Networks (ICCS 2023), Springer LNNS vol. 1032 | 2024 | link.springer.com/chapter/10.1007/978-981-99-3608-3_1 ; two independent search snippets agreeing on authors/venue/year (publisher page did not return full text to automated fetch) |
| Intelligent Threat Detection — AI-Driven Analysis of Honeypot Data to Counter Cyber Threats (`lanka2024intelligent`) | Poojitha Lanka, Kishor Datta Gupta, Cihan Varol | Electronics 13(13), article 2465 | 2024 | mdpi.com/2079-9292/13/13/2465 ; two independent search snippets agreeing on authors/venue/year (MDPI page returned 403 to automated fetch, confirmed instead via doi.org/10.3390/electronics13132465 metadata and a second independent snippet) |

These two are the "at least two concrete recent systems (2023-2026) that retrain a detector on
honeypot data" cited in §1: `matcheswala2024creating` trains a network traffic classifier on
honeypot-labelled traffic as part of an adaptive defense architecture, and `lanka2024intelligent`
applies AI/ML analysis to honeypot-collected data for threat detection. Neither paper evaluates
whether an adversary who knows the labelling policy can corrupt that channel — that gap is
exactly our threat model.

## B. Adaptive / LLM honeypots

| Title | Authors | Venue | Year | Checked |
|---|---|---|---|---|
| HoneyLLM: A Large Language Model-Powered Medium-Interaction Honeypot (`fan2024honeyllm`) | Wenjun Fan, Zichen Yang, Yuanzhen Liu, Lang Qin, Jia Liu | ICICS 2024, LNCS 15057 | 2024 | dblp.org/rec/conf/icics/FanYLQL24.html |
| HoneyGPT: Breaking the Trilemma in Terminal Honeypots with Large Language Model (`wang2024honeygpt`) | Ziyang Wang, Jianzhou You, Haining Wang | arXiv:2406.01882 (journal version: Computer Networks, 2026) | 2024 | arxiv.org/abs/2406.01882 |
| LLM Honeypot: Leveraging Large Language Models as Advanced Interactive Honeypot Systems (`otal2024llmhoneypot`) | Hakan T. Otal, M. Abdullah Canbaz | arXiv:2409.08234 | 2024 | arxiv.org/abs/2409.08234 |
| Adaptive Honeypot Engagement through Reinforcement Learning of Semi-Markov Decision Processes (`huang2019adaptive`) | Linan Huang, Quanyan Zhu | GameSec 2019 (DOI 10.1007/978-3-030-32430-8_13) | 2019 | arxiv.org/abs/1906.12182 |
| SoK: Honeypots & LLMs, More Than the Sum of Their Parts? (`bridges2025sok`) | Robert A. Bridges, Thomas R. Mitchell, Mauricio Muñoz, Ted Henriksson | arXiv:2510.25939 | 2025 | arxiv.org/abs/2510.25939 |
| Gotta Catch 'em All: A Multistage Framework for Honeypot Fingerprinting (`srinivasa2023gotta`) | Shreyas Srinivasa, Jens Myrup Pedersen, Emmanouil Vasilomanolakis | ACM Digital Threats: Research and Practice 4(3), article 42 | 2023 | dl.acm.org/doi/10.1145/3584976 ; arxiv.org/abs/2109.10652 |

## C. Poisoning of network / ML classifiers (attacks)

Deliberately includes pre-2015 work: the mechanism we attack (an automated learner trained on
traffic an attacker can shape) is old, even though "honeypot" and "LLM" are not.

| Title | Authors | Venue | Year | Checked |
|---|---|---|---|---|
| Paragraph: Thwarting Signature Learning by Training Maliciously (`newsome2006paragraph`) | James Newsome, Brad Karp, Dawn Song | RAID 2006, LNCS 4219, pp. 81–105 | 2006 | link.springer.com/chapter/10.1007/11856214_5 |
| Misleading Worm Signature Generators Using Deliberate Noise Injection (`perdisci2006misleading`) | Roberto Perdisci, David Dagon, Wenke Lee, Prahlad Fogla, Monirul Sharif | IEEE Symposium on Security and Privacy 2006 | 2006 | wenke.gtisc.gatech.edu/papers/ieee-sp-06.pdf (IEEE S&P 2006 program) |
| Exploiting Machine Learning to Subvert Your Spam Filter (`nelson2008exploiting`) | Blaine Nelson, Marco Barreno, Fuching Jack Chi, Anthony D. Joseph, Benjamin I. P. Rubinstein, Udam Saini, Charles Sutton, J. D. Tygar, Kai Xia | USENIX LEET 2008 | 2008 | usenix.org/legacy/event/leet08/tech/full_papers/nelson/nelson.pdf |
| Poisoning Attacks against Support Vector Machines (`biggio2012poisoning`) | Battista Biggio, Blaine Nelson, Pavel Laskov | ICML 2012 | 2012 | arxiv.org/abs/1206.6389 ; dblp.org/rec/conf/icml/BiggioNL12.html |
| ANTIDOTE: Understanding and Defending against Poisoning of Anomaly Detectors (`rubinstein2009antidote`) | Benjamin I. P. Rubinstein, Blaine Nelson, Ling Huang, Anthony D. Joseph, Shing-hon Lau, Satish Rao, Nina Taft, J. D. Tygar | ACM IMC 2009 | 2009 | dl.acm.org/doi/10.1145/1644893.1644895 |
| Security Analysis of Online Centroid Anomaly Detection (`kloft2012security`) | Marius Kloft, Pavel Laskov | JMLR 13, pp. 3681–3724 | 2012 | jmlr.org/papers/v13/kloft12b.html ; arxiv.org/abs/1003.0078 |

## D. Poisoning defenses (generic)

| Title | Authors | Venue | Year | Checked |
|---|---|---|---|---|
| Can Machine Learning Be Secure? (`barreno2006can`) | Marco Barreno, Blaine Nelson, Russell Sears, Anthony D. Joseph, J. D. Tygar | ASIACCS 2006 | 2006 | dl.acm.org/doi/10.1145/1128817.1128824 |
| Label Sanitization against Label Flipping Poisoning Attacks (`paudice2018label`) | Andrea Paudice, Luis Muñoz-González, Emil C. Lupu | arXiv:1803.00992 (ECML-PKDD Nemesis workshop, 2018) | 2018 | arxiv.org/abs/1803.00992 |
| Wild Patterns: Ten Years After the Rise of Adversarial Machine Learning (`biggio2018wild`) | Battista Biggio, Fabio Roli | Pattern Recognition, 2018 | 2018 | arxiv.org/abs/1712.03141 |
| Wild Patterns Reloaded: A Survey of Machine Learning Security against Training Data Poisoning (`cina2023wild`) | Antonio Emanuele Cinà, Kathrin Grosse, Ambra Demontis, Sebastiano Vascon, Werner Zellinger, Bernhard A. Moser, Alina Oprea, Battista Biggio, Marcello Pelillo, Fabio Roli | ACM Computing Surveys | 2023 | arxiv.org/abs/2205.01992 |

## E. IDS dataset critiques

| Title | Authors | Venue | Year | Checked |
|---|---|---|---|---|
| Troubleshooting an Intrusion Detection Dataset: the CICIDS2017 Case Study (`engelen2021troubleshooting`) | Gints Engelen, Vera Rimmer, Wouter Joosen | IEEE Security and Privacy Workshops (SPW) 2021, pp. 7–12 | 2021 | intrusion-detection.distrinet-research.be/WTMC2021 ; ieeexplore.ieee.org/document/9474286 |
| Errors in the CICIDS2017 Dataset and the Significant Differences in Detection Performances It Makes (`lanvin2022errors`) | Maxime Lanvin, Pierre-François Gimenez, Yufei Han, Frédéric Majorczyk, Ludovic Mé, Eric Totel | CRiSIS 2022 (Springer LNCS, 2023) | 2022 | pfgimenez.fr/publications/2022-CRiSIS/ ; dl.acm.org/doi/10.1007/978-3-031-31108-6_2 |
| Network Intrusion Detection: A Comprehensive Analysis of CIC-IDS2017 (`rosay2022network`) | Arnaud Rosay, Eloïse Cheval, Florent Carlier, Pascal Leroux | ICISSP 2022, pp. 25–36 | 2022 | scitepress.org/Papers/2022/107740/107740.pdf ; researchr.org/publication/RosayCCL22 |

## F. Adjacent: federated / online-learning IDS poisoning, and shadow honeypots

| Title | Authors | Venue | Year | Checked |
|---|---|---|---|---|
| Personalized Federated Learning-Based Intrusion Detection System: Poisoning Attack and Defense (`thein2024personalized`) | Thanoun Thein, Yoshiaki Shiraishi, Masakatu Morii | Future Generation Computer Systems 153, pp. 182–192 | 2024 | sciencedirect.com/science/article/pii/S0167739X23003783 (title/authors/venue/year cross-confirmed by two independent search snippets; the page itself 403'd an automated fetch) |
| Detecting Targeted Attacks Using Shadow Honeypots (`anagnostakis2005shadow`) | Kostas G. Anagnostakis, Stelios Sidiroglou, Periklis Akritidis, Konstantinos Xinidis, Evangelos Markatos, Angelos D. Keromytis | USENIX Security 2005 | 2005 | usenix.org/legacy/event/sec05/tech/full_papers/anagnostakis/anagnostakis.pdf |

---

## Overlap with our threat model, and how we differ

Eight of the 24 above bear directly enough on "a system that learns from traffic an attacker
can influence, and an attack on that" to need an explicit differentiation. None of them states
our core argument — that the auto-labeling *policy* itself ("everything the honeypot sees is
malicious") is the vulnerability, independent of what statistical mechanism sits behind it,
applied to a modern flow-based NIDS retraining loop, with benign-mimicry as the instantiated
attack and a cost-of-influence defense measured against a no-skill share-cap baseline.

- **Newsome, Karp & Song, "Paragraph" (RAID 2006)** and **Perdisci et al. (IEEE S&P 2006)** —
  closest older analog. Polygraph's worm-signature learner is trained on flows a honeynet or IDS
  flags as suspicious; both papers attack that channel with crafted noise. Differs: the target
  is a signature-matching detector for one specific worm, not a retrained statistical classifier
  scored on unrelated production traffic; the goal is evading detection of that worm, not
  raising false positives elsewhere; there is no persistent multi-round retraining loop with an
  accumulating poison share, which is the object our recovery/retention frontier measures.
- **Nelson et al., spam filter (USENIX LEET 2008)** — the closest continuous-retraining analog:
  an attacker with write access to ~1% of a Bayesian filter's training data (via messages that
  become labeled training examples) degrades it, and the filter keeps retraining on that
  stream. Differs: the write channel is user feedback / inbox placement, not a honeypot with a
  public, deterministic "everything here is malicious" labeling policy the attacker can read in
  advance; there is no decoy system and no attacker-cost accounting.
- **Rubinstein et al., ANTIDOTE (IMC 2009)** and **Kloft & Laskov (JMLR 2012)** — online/
  continuously-updated anomaly detectors poisoned by traffic the attacker injects, which is
  structurally our "loop." Differs: the poisoned traffic is real production traffic the detector
  monitors directly; there is no honeypot, no deception element, and no public labeling policy
  to exploit — the attacker must evade the anomaly detector's own scoring to get poison
  admitted, rather than simply reaching a decoy that labels everything malicious by design.
- **Barreno et al., "Can Machine Learning Be Secure?" (ASIACCS 2006)** — the foundational
  taxonomy this whole line of work sits inside (causative/exploratory, targeted/indiscriminate
  attacks; the RONI defense). Differs: a general framework with no honeypot-specific threat
  model or labeling-policy argument; we specialize one causative-attack instance end to end.
- **Yugai & Moskvin (2024)** and **HoneyModels (Abdou et al., MILCOM 2021)** — the two papers
  that put "honeypot" and "machine learning" together most literally, and the closest
  terminology match, but both point the other way. Yugai & Moskvin use a honeypot plus an ML
  classifier to *detect adversarial attacks against the IDS itself* (evasion of the classifier),
  not to question whether honeypot-derived training labels can be trusted. HoneyModels deploys
  ML models *as* decoys, to attract and study adversarial examples against the model — the
  honeypot is the model, not a data source feeding one. Neither treats the honeypot's output as
  an adversarial input channel into a defender's training set.
- **Paudice, Muñoz-González & Lupu, kNN label sanitization (2018)** — the same mechanism as our
  kNN comparator baseline (Section 7): relabel/drop points whose neighbourhood disagrees.
  Differs: evaluated against generic label-flipping poisoning, not a honeypot-sourced channel
  whose poison is consistent with the defender's own labeling policy; it does not surface the
  policy-consistency blind spot we report for loss-based filtering, because its threat model has
  no "the label is wrong but policy-consistent" case to fail on.
- **Srinivasa et al., honeypot fingerprinting (ACM DTRAP 2023)** — an attacker identifying
  honeypots to evade or selectively engage them. Relevant to A4 (fingerprint-and-split) and D3
  (persona randomization), which are out of this paper's scope, not to A1: fingerprinting
  decides *whether* to send traffic to the decoy, not what happens to the labels once it does.
