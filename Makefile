# Deception Loop — make targets
# Targets required by CLAUDE.md: demo, test, sim, experiment-<id>, figures, clean.
# demo and sim both forward to scripts/run.py, the actual cross-platform (incl. Windows) entry
# point -- see docs/DEMO.md. figures/paper are implemented -- see experiments/paper_figures.py.

UV ?= uv

.PHONY: help sync test phase0-explore phase0-models phase0-results sim demo figures paper clean

help:
	@echo "sync            install dependencies (uv sync)"
	@echo "test            run pytest"
	@echo "phase0-explore  feature distributions + cleaning drop report (synthetic)"
	@echo "sim             offline loop simulator on synthetic data (experiments/phase0_loop.py)"
	@echo "demo            live dashboard, recorded mode (python scripts/run.py demo --recorded)"
	@echo "figures         regenerate paper figures from committed CSVs (no re-runs)"
	@echo "paper           figures + compile paper/main.tex with Tectonic"
	@echo "clean           remove caches and generated artifacts (keeps results/ and data/)"

sync:
	$(UV) sync

test:
	$(UV) run pytest

phase0-explore:
	$(UV) run python -m experiments.phase0_explore --source synthetic --out results/phase0

phase0-models:
	$(UV) run python -m experiments.phase0_models --source synthetic --out results/phase0

phase0-grid-sweep:
	$(UV) run python -m experiments.phase0_grid_sweep --source synthetic --out results/phase0

phase0-results: phase0-explore phase0-models phase0-grid-sweep
	$(UV) run pytest -o addopts="-rN" -v | tee results/phase0/tests.txt

sim:
	$(UV) run python -m experiments.phase0_loop --dataset synthetic --scenarios control s0 a1 --out results/phase0/loop/sim_demo

demo:
	$(UV) run python scripts/run.py demo --recorded

figures:
	$(UV) run python scripts/run.py figures

paper: figures
	.tools/tectonic.exe -X compile paper/main.tex --outdir paper

experiment-%:
	$(UV) run python -m experiments.$*

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ src/**/__pycache__
