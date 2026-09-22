# Deception Loop

A network intrusion detection system that retrains itself on honeypot-derived labels, and a
research harness that shows why that design is attackable. The system is a working loop: flow
capture, ML detection, an integrated honeypot, auto-labeling, periodic retraining, and a live
dashboard. The research argues that auto-labeling a honeypot's traffic and feeding it into
retraining opens a write channel into the defender's own training set, because the attacker
controls exactly what the decoy sees and the labeling policy ("everything the honeypot sees is
malicious") has to be public for the honeypot to do its job. Both live in one codebase: the
offline simulator that produced every number in the paper (`experiments/`, `results/`) shares
its loop, model, and defense code with the live demo (`src/dloop/`), so a finding here is a
finding about the system, not about a separate toy.

## Headline findings

- **The honest loop works.** Clean honeypot traffic (genuine attacks, correctly labeled) improves
  the detector within 1-2 rounds — the sanity check the rest of the paper depends on
  (`paper/sections/06_attack.tex`, "S0").
- **Benign-mimicry poisoning (A1) needs near-duplicate fidelity, not model access.** Point a
  traffic generator that produces realistic benign flows at the honeypot instead of production;
  the auto-labeler stamps it malicious; the false-positive rate on real users climbs. The effect
  is a cliff, not a gradient — see **Figure 3** (`F3_damage_vs_fidelity`), and the *twin
  fraction* statistic in `paper/sections/03_threat_model.tex`/`06_attack.tex` that resolves where
  the cliff actually sits (a simple median distance cannot).
- **One mechanism, not two channels.** The threshold policy decides whether the damage shows up
  as false positives or as lost detection — recalibrating relocates the damage, it does not
  remove it (**Figure 4**, `F4_a1_trajectory`; **Figure 5**, `F5_mechanism_isolation`, the
  matched-null-control isolation of the mechanism).
- **A generic label-consistency defense fails structurally**, because the poison agrees with the
  defender's own labeling policy — it isn't inconsistent with anything the loop believes
  (`paper/sections/07_defenses.tex`, "the policy-consistency blind spot").
- **A one-line cap on the honeypot's training-set share (ShareCap) is undominated by every
  defense we test** — no alternative, including our own original proposal (cost-of-influence
  weighting, a measured negative result), is at least as good on both recovery and retention —
  at close to zero cost, with no label information, no trusted reference data, and no knowledge
  of the poison ratio (**Figure 6**, `F6_frontier`).
- **CICIDS2017's own benign traffic is unusually repetitive**, which is why the attack is cheap
  to demonstrate on this specific benchmark (`paper/sections/05_degeneracy.tex`) — a property of
  the dataset, not a general claim about production network traffic.

Full writeup, every number sourced to a committed CSV or a `docs/DECISIONS.md` section: the
compiled paper is `paper/main.pdf` (`make paper` to rebuild).

## Quickstart

```
uv sync
uv run pytest              # or: make test
python scripts/run.py demo --recorded   # dashboard at http://127.0.0.1:8000, no training required
```

`--recorded` replays a captured run (`results/demo/recorded.json`, committed) with no CICIDS data
and no retraining — the fastest way to see the loop, the poisoning, and the defenses without
setting anything up. Drop `--recorded` for the live version, which runs the real loop code
against real CICIDS2017 flows (needs the data — see below). See **`docs/DEMO.md`** for a full
walkthrough script (what to click, what to say, what breaks and how to recover).

## Reproducing the paper

```
python scripts/run.py figures     # regenerates every figure in paper/figures/ from committed CSVs
make paper                        # figures + compile paper/main.tex with Tectonic
```

No experiment needs to be re-run to reproduce a figure — every number traces to a CSV already
committed under `results/`, and the exact command that regenerates each figure is named in a
LaTeX comment above that figure in `paper/sections/*.tex`. To reproduce the underlying
*experiments* instead of just the figures (i.e. to regenerate the CSVs themselves), see
`docs/DECISIONS.md` — every numbered section there records the exact command, config, and result
for the run it describes, in the order the project was actually built. `docs/PAPER_PLAN.md` maps
paper sections to their source `DECISIONS.md` sections and CSVs if you want to go the other
direction (I have a claim, where did it come from).

## Getting CICIDS2017 (optional — synthetic works with no downloads)

Every test, every figure, and the S0 (clean-loop) learning claim run on a synthetic generator
built into the codebase — nothing above needs CICIDS2017. CICIDS2017 is only needed for the A1
damage-vs-fidelity numbers and the degeneracy measurement, both reproducible from the CSVs
already committed under `results/phase0/cicids/` without re-downloading anything.

To re-run those experiments from raw data: download the **`MachineLearningCVE`** CSV set (the
pre-extracted flow-feature CSVs, *not* the raw PCAPs and *not* `GeneratedLabelledFlows`) from the
[University of New Brunswick CIC IDS-2017 page](https://www.unb.ca/cic/datasets/ids-2017.html)
(registration required). Extract the eight `*.pcap_ISCX.csv` files (one per weekday session,
~844 MB total) into `data/cicids2017/` at the repo root — that directory is gitignored, so
nothing you put there gets committed. Pass `--source cicids` to the relevant `experiments/*.py`
script once the files are in place.

## Repo layout

```
src/dloop/       the live system: capture, honeypot, features, models, loop, defense, api, demo
experiments/     one script per research question; phase0_*.py run experiments, paper_figures.py
                 regenerates every figure from committed CSVs (no re-runs)
results/         committed CSV/JSON outputs — the source of truth every paper number traces to
paper/           the LaTeX paper (main.tex, sections/, figures/, references.bib)
docs/            DECISIONS.md (methodology + findings log), PAPER_PLAN.md (claim -> source map),
                 RELATED_WORK.md (verified bibliography), DEMO.md (live walkthrough script),
                 ARXIV.md (submission metadata, prepared not submitted)
scripts/         run.py (the demo/test/figures entry point), attack_honeypot.py (lab-only,
                 127.0.0.1-only — see the warning at the top of the file), cowrie/ (honeypot setup)
tests/           pytest suite; the live demo (test_live.py) asserts it reproduces the archived
                 experiments row for row, same code path
dashboard/       Jinja + HTMX + Chart.js templates for the live dashboard (no build step)
data/            gitignored; CICIDS2017 goes here if you want to reproduce from raw data
```

`CLAUDE.md` is the fuller architecture/threat-model/phase-plan document this project was built
against.

## Hardware and runtime expectations

Developed and tested on a modest machine (7.7 GB RAM). `uv sync`, `pytest`, `scripts/run.py
figures`, and `scripts/run.py demo --recorded` each take well under a minute. The offline
experiments this repo's results were built from do not: a damage-vs-fidelity sweep is a
brute-force nearest-neighbour query over the full trusted-eval set per jitter setting, and a
defense-comparison sweep retrains models across a ratio grid — either can run from tens of
minutes to a few hours depending on grid size, and hold several hundred MB to a few GB of memory
per worker. On a RAM-constrained machine, cap parallel sweep workers at 2-4
(`experiments/phase0_loop.py --workers N`, the script behind most of this paper's headline
numbers) — pushing higher risks an `OpenBLAS`/`numpy` allocation failure mid-sweep, which costs
more than the parallelism saves. CICIDS2017 itself is ~844 MB on disk;
the committed `results/` CSVs are ~150 MB.

## License

MIT — see `LICENSE`. The paper (`paper/`) is intended for arXiv release under CC BY 4.0 (see
`docs/ARXIV.md`), independent of the code's license.
