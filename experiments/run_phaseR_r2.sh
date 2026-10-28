#!/usr/bin/env bash
# Phase R item R2 (ShareCap generality), DECISIONS.md §31.2.
#   bash experiments/run_phaseR_r2.sh cicids         # pairs (b)+(c), R2.3 srcpart, R2.4 crowd-out
#   bash experiments/run_phaseR_r2.sh cicids-fixed   # pairs (a)
#   bash experiments/run_phaseR_r2.sh unsw-nb15      # pairs (a)
# Run in that order, each under nohup with its own log (docs/phaseR/session-r2.md).
# Resumes from existing job files; re-run the same command after any interruption.
# Smoke test: SMOKE=1 ROOT=.smoke/phaseR bash experiments/run_phaseR_r2.sh <dataset>
set -euo pipefail
PYTHON=${PYTHON:-python}
ROOT=${ROOT:-results/phaseR}
WORKERS=${WORKERS:-3}
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

DATASET=${1:?usage: run_phaseR_r2.sh <cicids|cicids-fixed|unsw-nb15>}
case "$DATASET" in
  cicids)                  TAU=0.1; MODELS="rf xgboost logreg mlp" ;;
  cicids-fixed|unsw-nb15)  TAU=0;   MODELS="rf xgboost" ;;   # Phase A's measured tau (§30.B)
  *) echo "unknown dataset $DATASET" >&2; exit 2 ;;
esac
OUT="$ROOT/r2/$DATASET"

loop() {  # loop <phase0_loop args...>   (15 seeds throughout R2)
  local seeds=15
  if [ "${SMOKE:-0}" = 1 ]; then seeds=1; set -- "$@" --rounds 2; fi
  echo ">>> phase0_loop --seeds $seeds $*"
  "$PYTHON" -m experiments.phase0_loop --dataset "$DATASET" --val-nn-tau "$TAU" --out "$OUT" \
    --seeds "$seeds" --workers "$WORKERS" --no-fidelity "$@"
}

# R2.1  control once per model (no defense can act on it), then A1 + S0 under each defense
# shellcheck disable=SC2086
loop --scenarios control --models $MODELS
for DEF in "none" "sharecap --share-cap 0.02" "sharecap --share-cap 0.05" \
           "sharecap --share-cap 0.1" "sharecap --share-cap 0.2" "uniform --uniform-w 0.05"; do
  # shellcheck disable=SC2086
  loop --scenarios a1 --models $MODELS --jitters 0 --ratios 0.2 0.5 0.9 --defense $DEF
  # shellcheck disable=SC2086
  loop --scenarios s0 --models $MODELS --ratios 0.2 --defense $DEF
done

if [ "$DATASET" = cicids ]; then
  # R2.3  source-partition baseline, pairs (c) only
  loop --scenarios a1 --models rf xgboost --jitters 0 --ratios 0.2 0.5 0.9 --defense srcpart --sp-alpha 0.5
  loop --scenarios s0 --models rf xgboost --ratios 0.2 --defense srcpart --sp-alpha 0.5
  # R2.4  crowd-out against ShareCap c=0.05 (S0 m=0 arms are the R2.1 s0 runs above)
  for M in 1 4 9; do
    for DEF in "none" "sharecap --share-cap 0.05"; do
      # shellcheck disable=SC2086
      loop --scenarios s0crowd --models rf xgboost --ratios 0.2 --crowd-factor "$M" \
        --crowd-jitter 0.7 --defense $DEF
    done
  done
fi

echo "R2 runs complete for $DATASET"
