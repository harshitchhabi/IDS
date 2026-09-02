# Deception Loop

A deception-aware network intrusion detection system that continuously retrains
itself from honeypot-derived labels, plus a research harness that attacks that
design and defends it.

See [CLAUDE.md](CLAUDE.md) for architecture, threat model, and phase plan.

## Setup

```
uv sync
make test
```

## Current status: Phase 0 — offline simulator, data layer

```
make phase0-explore   # feature distributions + cleaning drop report on synthetic data
```

The whole pipeline runs on synthetic data with no external downloads. To use the
real CICIDS2017 CSVs, drop the `MachineLearningCVE/*.csv` files into
`data/cicids2017/` and pass `--source cicids`.
