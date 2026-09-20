#!/bin/bash
# Far-distance mechanism sweeps (DECISIONS.md 22). 3 workers: the machine has ~400 MB free beyond them.
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH="src;."
PY=.venv/Scripts/python.exe; R=results/phase0/loop
NEW="experiments/phase0_loop.py --dataset cicids --val-nn-tau 0.1 --workers 3 --out $R/cicids_recal --no-fidelity"
OLD="experiments/phase0_loop.py --dataset cicids --workers 3 --out $R/cicids --no-fidelity"
RAT="--ratios 0.02 0.05 0.2 0.5"
# A. ratio sweep at fixed high distance, honest calibration: benign-poison, matched attack rows, true labels, junk
$PY $NEW --scenarios a1 s0j a1truth --jitters 1.5 $RAT > far_new_jit.log 2>&1; echo EXIT=$? >> far_new_jit.log
$PY $NEW --scenarios junk $RAT > far_new_junk.log 2>&1; echo EXIT=$? >> far_new_junk.log
echo A > far_a.flag
# B. old calibration: matched attack rows and junk (a1 at jitter 1.5 already exists there)
$PY $OLD --scenarios s0j junk --jitters 1.5 $RAT > far_old.log 2>&1; echo EXIT=$? >> far_old.log
echo B > far_b.flag
# C. defenses in the far-distance regime, honest calibration
for d in d1 knn loss; do
  $PY $NEW --scenarios a1 --defense $d --jitters 1.5 --ratios 0.2 0.5 > far_def_a1_$d.log 2>&1; echo EXIT=$? >> far_def_a1_$d.log
  $PY $NEW --scenarios junk --defense $d --ratios 0.2 0.5 > far_def_junk_$d.log 2>&1; echo EXIT=$? >> far_def_junk_$d.log
done
echo ALL > far_done.flag
