# Phase 0 determinism & sample_weight evidence

Small fast estimators (reproducibility depends on seeding, not model size).

## Two identical-seed runs produce identical predictions

| model | max abs delta score_samples | thresholds equal | predictions equal |
|---|---|---|---|
| rf | 0.00e+00 | True | True |
| xgboost | 0.00e+00 | True | True |
| autoencoder | 0.00e+00 | True | True |

## sample_weight changes every fitted model

Zero-weight all attack rows (autoencoder: the high-fwd_bytes benign half); refit; compare on trusted_eval.

| model | mean abs delta score | predictions changed | frac flipped |
|---|---|---|---|
| rf | 0.0118 | True | 0.2975 |
| xgboost | 0.0039 | True | 0.2108 |
| autoencoder | 0.6173 | True | 0.0216 |

## save / load round-trip

| model | scores identical | threshold identical |
|---|---|---|
| rf | True | True |
| xgboost | True | True |
| autoencoder | True | True |
