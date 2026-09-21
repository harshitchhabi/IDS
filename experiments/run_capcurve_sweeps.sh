#!/bin/bash
# ShareCap cap-sensitivity curve (DECISIONS.md 25.5): the full curve, not a chosen range. 2 workers so the demo keeps its RAM.
# c = 0.03, 0.05, 0.08 already exist from run_sharecap_sweeps.sh; the job files resume, so they are skipped.
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src;."
PY=.venv/Scripts/python.exe; R=results/phase0/loop
C="experiments/phase0_loop.py --dataset cicids --val-nn-tau 0.1 --workers 2 --out $R/cicids_recal --no-fidelity"
S="experiments/phase0_loop.py --dataset synthetic --workers 2"
run() { $PY "$@" > /dev/null 2>&1; }
for c in 0.01 0.02 0.1 0.15 0.2 0.3 0.5; do
  run $C --scenarios a1 --models xgboost --ratios 0.5 0.9 --jitters 0 --defense sharecap --share-cap $c
  run $C --scenarios s0 --models xgboost --ratios 0.2 --defense sharecap --share-cap $c
  run $S --scenarios s0 --models xgboost --ratios 0.05 0.2 --defense sharecap --share-cap $c
  echo "$c" > capcurve_$c.flag
done
echo ALL > capcurve_done.flag
