# Deception Loop — make targets
# Targets required by CLAUDE.md: demo, test, sim, experiment-<id>, figures, clean
# (demo/sim/figures are stubs until their phase lands.)

UV ?= uv

.PHONY: help sync test phase0-explore phase0-models phase0-results sim demo figures clean

help:
	@echo "sync            install dependencies (uv sync)"
	@echo "test            run pytest"
	@echo "phase0-explore  feature distributions + cleaning drop report (synthetic)"
	@echo "sim             offline simulator (Phase 0, not yet implemented)"
	@echo "demo            docker testbed (Phase 1+, not yet implemented)"
	@echo "figures         regenerate paper figures (Phase 6)"
	@echo "clean           remove caches and generated artifacts"

sync:
	$(UV) sync

test:
	$(UV) run pytest

phase0-explore:
	$(UV) run python -m experiments.phase0_explore --source synthetic --out results/phase0

phase0-models:
	$(UV) run python -m experiments.phase0_models --source synthetic --out results/phase0

phase0-results: phase0-explore phase0-models
	$(UV) run pytest -o addopts="-rN" -v | tee results/phase0/tests.txt

sim:
	@echo "sim: not implemented until Phase 0 loop simulator lands"; exit 1

demo:
	@echo "demo: not implemented until Phase 1"; exit 1

figures:
	@echo "figures: not implemented until Phase 6"; exit 1

experiment-%:
	$(UV) run python -m experiments.$*

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ src/**/__pycache__
	rm -rf results/phase0
