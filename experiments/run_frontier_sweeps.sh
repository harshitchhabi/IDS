#!/bin/bash
# Recovery/utility frontier (DECISIONS.md 24). XGBoost, 5 seeds, 3 workers.
#   recovery axis : A1 copy fidelity (jitter 0), ratio 0.5, CICIDS, honest calibration (tau 0.1)
#   retention axis: S0 on synthetic, ratios 0.05 and 0.2
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src;."
PY=.venv/Scripts/python.exe; R=results/phase0/loop
A1="experiments/phase0_loop.py --dataset cicids --val-nn-tau 0.1 --workers 3 --out $R/cicids_recal --no-fidelity --scenarios a1 --models xgboost --ratios 0.5 --jitters 0"
S0="experiments/phase0_loop.py --dataset synthetic --workers 3 --scenarios s0 --models xgboost --ratios 0.05 0.2"
run() { $PY "$@" > /dev/null 2>&1; }

# 1. no-skill line: uniform weights
for w in 0.05 0.1 0.25 0.5; do
  run $S0 --defense uniform --uniform-w $w
  run $A1 --defense uniform --uniform-w $w
done
echo U > fr_uniform.flag
# 2. utility of the pre-registered E* x gamma grid (recovery already exists at ratio 0.5)
for e in 2 4 8 16 32; do for g in 1 2 3; do
  [ "$e" = "8" ] && [ "$g" = "2" ] && continue     # default already run
  run $S0 --defense d1 --d1-estar $e --d1-gamma $g
done; done
echo B > fr_base.flag
# 3. quantile-anchored E*
for q in 0.5 0.75 0.9 0.95 0.99; do for g in 1 2; do
  run $S0 --defense d1 --d1-quantile $q --d1-gamma $g
  run $A1 --defense d1 --d1-quantile $q --d1-gamma $g
done; done
echo Q > fr_quant.flag
# 4. fixed reference units (needs no trusted data)
for e in 4 8 16 32; do
  run $S0 --defense d1 --d1-reference fixed --d1-estar $e --d1-gamma 2
  run $A1 --defense d1 --d1-reference fixed --d1-estar $e --d1-gamma 2
done
echo ALL > fr_done.flag
