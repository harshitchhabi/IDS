#!/usr/bin/env bash
# Phase R item R3 (UQ NetFlow v2), DECISIONS.md §31.3. Two stages per dataset:
#   bash experiments/run_phaseR_r3.sh <dataset> prep         # cache, grid sweep, degeneracy, tau sweep
#   bash experiments/run_phaseR_r3.sh <dataset> main <tau>   # R3.1, R3.2, R3.3 at the measured tau
# <dataset>: nf-unsw-nb15-v2 | nf-cse-cic-ids2018-v2 | nf-ton-iot-v2
# Resumes from existing job files; re-run the same command after any interruption.
# Smoke test: SMOKE=1 ROOT=.smoke/phaseR bash experiments/run_phaseR_r3.sh <dataset> prep|main <tau>
set -euo pipefail
PYTHON=${PYTHON:-python}
ROOT=${ROOT:-results/phaseR}
WORKERS=${WORKERS:-3}
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

DATASET=${1:?usage: run_phaseR_r3.sh <dataset> prep|main <tau>}
STAGE=${2:?usage: run_phaseR_r3.sh <dataset> prep|main <tau>}
OUT="$ROOT/r3/$DATASET"
mkdir -p "$OUT"

loop() {  # loop <seeds> <phase0_loop args...>
  local seeds=$1; shift
  if [ "${SMOKE:-0}" = 1 ]; then seeds=1; set -- "$@" --rounds 2; fi
  echo ">>> phase0_loop --seeds $seeds $*"
  "$PYTHON" -m experiments.phase0_loop --dataset "$DATASET" --seeds "$seeds" \
    --workers "$WORKERS" --no-fidelity "$@"
}

if [ "$STAGE" = prep ]; then
  "$PYTHON" -m experiments.phase0_loop_data --source "$DATASET"
  "$PYTHON" -m experiments.phase0_grid_sweep --source "$DATASET" --out "$OUT"
  "$PYTHON" -m experiments.phase0_degeneracy --source "$DATASET" --out "$OUT"
  # tau rule (§31.3): control, 5 seeds, both models, each tau on the fixed grid
  for TAU in 0 0.005 0.01 0.02 0.05 0.1 0.2; do
    loop 5 --val-nn-tau "$TAU" --scenarios control --models rf xgboost --out "$OUT/tau_sweep"
  done
  if [ "${SMOKE:-0}" = 1 ]; then
    echo "(smoke: tau floor needs rounds 11-20; skipped)"
  else
    "$PYTHON" -m experiments.phaseA_tau_floor "$OUT/tau_sweep"
  fi
  echo "R3 prep complete for $DATASET"
elif [ "$STAGE" = main ]; then
  TAU=${3:?main needs the tau chosen by the tau floor at the end of the prep stage}
  # R3.1  damage grid
  loop 15 --val-nn-tau "$TAU" --scenarios control a1 --models rf xgboost \
    --jitters 0 0.7 --ratios 0.2 0.5 --out "$OUT"
  # R3.2  mechanism isolation (a1 at ratio 0.2, jitter 0.7 comes from R3.1)
  loop 15 --val-nn-tau "$TAU" --scenarios a1truth s0j --models rf --jitters 0.7 --ratios 0.2 --out "$OUT"
  loop 15 --val-nn-tau "$TAU" --scenarios junk --models rf --jitters 0.0 --ratios 0.2 --out "$OUT"
  # R3.3  ShareCap c=0.05
  loop 15 --val-nn-tau "$TAU" --scenarios a1 --models rf xgboost --jitters 0 --ratios 0.2 0.5 \
    --defense sharecap --share-cap 0.05 --out "$OUT"
  echo "R3 main runs complete for $DATASET"
else
  echo "unknown stage $STAGE" >&2; exit 2
fi
