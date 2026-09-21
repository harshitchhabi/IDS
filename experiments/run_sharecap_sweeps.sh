#!/bin/bash
# ShareCap (DECISIONS.md 25.2): the no-skill baseline that works at any poison ratio. XGBoost, 5 seeds, 3 workers.
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src;."
PY=.venv/Scripts/python.exe; R=results/phase0/loop
C="experiments/phase0_loop.py --dataset cicids --val-nn-tau 0.1 --workers 3 --out $R/cicids_recal --no-fidelity"
S="experiments/phase0_loop.py --dataset synthetic --workers 3"
run() { $PY "$@" > /dev/null 2>&1; }
for c in 0.05 0.03 0.08; do
  run $C --scenarios s0 --models xgboost --ratios 0.2 --defense sharecap --share-cap $c
  run $S --scenarios s0 --models xgboost --ratios 0.05 0.2 --defense sharecap --share-cap $c
  run $C --scenarios a1 --models xgboost --ratios 0.5 0.9 --jitters 0 --defense sharecap --share-cap $c
  echo "$c" > sc_$c.flag
done
echo ALL > sc_done.flag
