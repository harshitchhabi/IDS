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
| rf | 0.1308 | True | 0.2078 |
| xgboost | 0.1425 | True | 0.1853 |
| autoencoder | 0.3217 | True | 0.0037 |

## save / load round-trip

| model | scores identical | threshold identical |
|---|---|---|
| rf | True | True |
| xgboost | True | True |
| autoencoder | True | True |
