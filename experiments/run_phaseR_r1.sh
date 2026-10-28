#!/usr/bin/env bash
# Phase R item R1 (power), DECISIONS.md §31.1. Runs R1.a, R1.b, R1.c in order.
# Resumes from existing job files; re-run the same command after any interruption.
#   nohup bash experiments/run_phaseR_r1.sh > results/phaseR/r1/run.log 2>&1 &
# Smoke test (1 seed, 2 rounds, scratch output):
#   SMOKE=1 ROOT=.smoke/phaseR bash experiments/run_phaseR_r1.sh
set -euo pipefail
PYTHON=${PYTHON:-python}
ROOT=${ROOT:-results/phaseR}
WORKERS=${WORKERS:-3}
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

loop() {  # loop <seeds> <phase0_loop args...>
  local seeds=$1; shift
  if [ "${SMOKE:-0}" = 1 ]; then seeds=1; set -- "$@" --rounds 2; fi
  echo ">>> phase0_loop --seeds $seeds $*"
  "$PYTHON" -m experiments.phase0_loop --seeds "$seeds" --workers "$WORKERS" --no-fidelity "$@"
}

# R1.a  36-cell grid, 15 seeds, eval subsample redrawn per seed
loop 15 --dataset cicids --val-nn-tau 0.1 --scenarios control a1 --models rf xgboost \
  --jitters 0 0.002 0.005 0.01 0.03 0.1 0.3 0.7 1.5 --ratios 0.2 0.5 \
  --eval-redraw --out "$ROOT/r1/grid36"

# R1.b  XGBoost bimodality, 30 seeds, default (fixed) eval subsample
loop 30 --dataset cicids --val-nn-tau 0.1 --scenarios control a1 --models xgboost \
  --jitters 0 --ratios 0.5 --out "$ROOT/r1/fixed"

# R1.c  RF mid-range jitters, 15 seeds, default (fixed) eval subsample (s26.6 protocol)
loop 15 --dataset cicids --val-nn-tau 0.1 --scenarios control a1 --models rf \
  --jitters 0.01 0.03 0.1 --ratios 0.2 0.5 --out "$ROOT/r1/fixed"

echo "R1 runs complete"
