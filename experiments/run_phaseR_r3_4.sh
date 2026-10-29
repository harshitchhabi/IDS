#!/usr/bin/env bash
# Phase R follow-up R3.4 (docs/phaseR/r3-followup-prereg.md): damage onset, then ShareCap below it.
#   bash experiments/run_phaseR_r3_4.sh <dataset> <tau>
# Writes into R3's own directory so R3's control, undefended A1 r=0.5 and ShareCap 0.05 jobs are
# reused (a job whose CSV exists is skipped). Resumes; re-run the same command after any interruption.
# Smoke test: SMOKE=1 ROOT=<scratch> bash experiments/run_phaseR_r3_4.sh <dataset> <tau>
set -euo pipefail
PYTHON=${PYTHON:-python}
ROOT=${ROOT:-results/phaseR}
WORKERS=${WORKERS:-3}
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

DATASET=${1:?usage: run_phaseR_r3_4.sh <dataset> <tau>}
TAU=${2:?usage: run_phaseR_r3_4.sh <dataset> <tau>}
OUT="$ROOT/r3/$DATASET"
mkdir -p "$OUT"

loop() {
  local seeds=15
  if [ "${SMOKE:-0}" = 1 ]; then seeds=1; set -- "$@" --rounds 2; fi
  echo ">>> phase0_loop --seeds $seeds $*"
  "$PYTHON" -m experiments.phase0_loop --dataset "$DATASET" --val-nn-tau "$TAU" --out "$OUT" \
    --seeds "$seeds" --workers "$WORKERS" --no-fidelity "$@"
}

loop --scenarios control --models rf xgboost
# stage a: onset
loop --scenarios a1 --models rf xgboost --jitters 0 --ratios 0.01 0.02 0.05 0.1
# stage b: A1 ratio 0.5, undefended and under each cap
loop --scenarios a1 --models rf xgboost --jitters 0 --ratios 0.5
for C in 0.005 0.01 0.02 0.05; do
  loop --scenarios a1 --models rf xgboost --jitters 0 --ratios 0.5 --defense sharecap --share-cap "$C"
done
# stage b: S0 retention
for DEF in "none" "sharecap --share-cap 0.005" "sharecap --share-cap 0.01" \
           "sharecap --share-cap 0.02" "sharecap --share-cap 0.05" "uniform --uniform-w 0.05"; do
  # shellcheck disable=SC2086
  loop --scenarios s0 --models rf xgboost --ratios 0.2 --defense $DEF
done
echo "R3.4 runs complete for $DATASET"
