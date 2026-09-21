#!/bin/bash
# Frontier follow-ups (DECISIONS.md 24): same-dataset retention, high-ratio robustness, RF checks.
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src;."
PY=.venv/Scripts/python.exe; R=results/phase0/loop
C="experiments/phase0_loop.py --dataset cicids --val-nn-tau 0.1 --workers 3 --out $R/cicids_recal --no-fidelity"
run() { $PY "$@" > /dev/null 2>&1; }
# 1. retention measured on CICIDS too (S0, XGBoost, ratio 0.2): every frontier point
S0C="$C --scenarios s0 --models xgboost --ratios 0.2"
for w in 0.05 0.1 0.25 0.5; do run $S0C --defense uniform --uniform-w $w; done
for e in 2 4 8 16 32; do for g in 1 2 3; do run $S0C --defense d1 --d1-estar $e --d1-gamma $g; done; done
for q in 0.5 0.75 0.9 0.95 0.99; do for g in 1 2; do run $S0C --defense d1 --d1-quantile $q --d1-gamma $g; done; done
for e in 4 8 16 32; do run $S0C --defense d1 --d1-reference fixed --d1-estar $e --d1-gamma 2; done
echo S0C > fu_s0c.flag
# 2. does the ordering survive a higher poison ratio? (A1 ratio 0.9, XGBoost)
A9="$C --scenarios a1 --models xgboost --ratios 0.9 --jitters 0"
run $A9 --defense knn
run $A9 --defense uniform --uniform-w 0.05
run $A9 --defense uniform --uniform-w 0.1
run $A9 --defense d1 --d1-quantile 0.99 --d1-gamma 1
run $A9 --defense d1 --d1-quantile 0.99 --d1-gamma 2
echo A9 > fu_a9.flag
# 3. RF checks on the points that matter
ARF="$C --scenarios a1 --models rf --ratios 0.5 --jitters 0"
SRF="experiments/phase0_loop.py --dataset synthetic --workers 3 --scenarios s0 --models rf --ratios 0.05 0.2"
run $ARF --defense uniform --uniform-w 0.1
run $ARF --defense d1 --d1-quantile 0.99 --d1-gamma 1
run $SRF --defense uniform --uniform-w 0.1
run $SRF --defense d1 --d1-quantile 0.99 --d1-gamma 1
echo ALL > fu_done.flag
