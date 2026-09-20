#!/bin/bash
# Defended sweeps, priority order. 3 workers (machine has ~400 MB free beyond the workers).
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src;."
PY=.venv/Scripts/python.exe; R=results/phase0/loop; L="experiments/phase0_loop.py --dataset cicids --val-nn-tau 0.1 --workers 3 --out $R/cicids_recal"
# 1. A1 at raw benign, main defended table
for d in knn d1 loss; do
  $PY $L --scenarios a1 --defense $d --ratios 0.05 0.1 0.2 0.5 --jitters 0 --no-fidelity > def_a1_$d.log 2>&1; echo EXIT=$? >> def_a1_$d.log
done
echo G1 > def_g1.flag
# 2. utility: S0 under each defense (CICIDS then synthetic)
for d in d1 knn loss; do
  $PY $L --scenarios s0 --defense $d --ratios 0.05 0.2 > def_s0c_$d.log 2>&1; echo EXIT=$? >> def_s0c_$d.log
  $PY experiments/phase0_loop.py --dataset synthetic --scenarios s0 --defense $d --ratios 0.05 0.2 --workers 3 > def_s0s_$d.log 2>&1; echo EXIT=$? >> def_s0s_$d.log
done
echo G2 > def_g2.flag
# 3. D1 attacker-cost curve beyond 0.5 (XGBoost only), undefended and D1
for d in none d1; do
  $PY $L --scenarios a1 --defense $d --models xgboost --ratios 0.8 0.9 --jitters 0 --no-fidelity > def_ext_$d.log 2>&1; echo EXIT=$? >> def_ext_$d.log
done
echo G3 > def_g3.flag
# 4. sensitivity grid (E* x gamma) and component ablation, XGBoost, ratio 0.5
for e in 2 4 8 16 32; do for g in 1 2 3; do
  $PY $L --scenarios a1 --defense d1 --models xgboost --ratios 0.5 --jitters 0 --d1-estar $e --d1-gamma $g --no-fidelity > def_sens_${e}_${g}.log 2>&1
done; done
for c in duration_s packets bytes depth; do
  $PY $L --scenarios a1 --defense d1 --models xgboost --ratios 0.5 --jitters 0 --d1-components $c --no-fidelity > def_abl_$c.log 2>&1
done
echo G4 > def_g4.flag
# 5. adversary padding, with fidelity
for p in 2 8 32; do for d in none d1; do
  $PY $L --scenarios a1 --defense $d --models xgboost --ratios 0.5 --jitters 0 --pad $p > def_pad_${d}_$p.log 2>&1
done; done
echo ALL > def_done.flag
