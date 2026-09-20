# Mechanism separation and recalibration (CICIDS2017)

Poison at realized NN ~0.56 (jitter 0.7); ratios (0.05, 0.2); 5 seeds; final round; deltas are same-seed differences against the control of the same calibration. `t_paired` = mean / (sd / sqrt(n)). Fixed threshold -> FPR; recalibrated -> TPR.

## OLD calibration (round-0 threshold on the raw validation split)

| model   | threshold_mode   |   poison_ratio | contrast                                            | delta            |     t |   2sigma_ctrl |
|:--------|:-----------------|---------------:|:----------------------------------------------------|:-----------------|------:|--------------:|
| rf      | fixed            |           0.05 | a1 (benign->malicious, jittered)                    | +0.038 +/- 0.005 |  16.5 |         0.03  |
| rf      | fixed            |           0.05 | a1truth (same rows, true label)                     | -0.010 +/- 0.013 |  -1.7 |         0.03  |
| rf      | fixed            |           0.05 | s0j (attack->malicious, jittered)                   | +0.013 +/- 0.010 |   2.9 |         0.03  |
| rf      | fixed            |           0.05 | s0 (attack->malicious)                              | +0.009 +/- 0.016 |   1.2 |         0.03  |
| rf      | fixed            |           0.05 | a1 - s0j  (label conflict beyond prior shift)       | +0.025 +/- 0.011 |   5   |         0.03  |
| rf      | fixed            |           0.05 | a1 - a1truth  (effect of the label flip, same rows) | +0.048 +/- 0.013 |   8.6 |         0.03  |
| rf      | fixed            |           0.2  | a1 (benign->malicious, jittered)                    | +0.054 +/- 0.008 |  15.8 |         0.03  |
| rf      | fixed            |           0.2  | a1truth (same rows, true label)                     | -0.016 +/- 0.013 |  -2.8 |         0.03  |
| rf      | fixed            |           0.2  | s0j (attack->malicious, jittered)                   | +0.021 +/- 0.016 |   3   |         0.03  |
| rf      | fixed            |           0.2  | s0 (attack->malicious)                              | +0.027 +/- 0.017 |   3.4 |         0.03  |
| rf      | fixed            |           0.2  | a1 - s0j  (label conflict beyond prior shift)       | +0.033 +/- 0.010 |   7.5 |         0.03  |
| rf      | fixed            |           0.2  | a1 - a1truth  (effect of the label flip, same rows) | +0.070 +/- 0.006 |  25   |         0.03  |
| rf      | recalibrated     |           0.05 | a1 (benign->malicious, jittered)                    | -0.085 +/- 0.025 |  -7.5 |         0.061 |
| rf      | recalibrated     |           0.05 | a1truth (same rows, true label)                     | +0.015 +/- 0.049 |   0.7 |         0.061 |
| rf      | recalibrated     |           0.05 | s0j (attack->malicious, jittered)                   | -0.003 +/- 0.030 |  -0.2 |         0.061 |
| rf      | recalibrated     |           0.05 | s0 (attack->malicious)                              | +0.058 +/- 0.032 |   4   |         0.061 |
| rf      | recalibrated     |           0.05 | a1 - s0j  (label conflict beyond prior shift)       | -0.083 +/- 0.018 | -10.4 |         0.061 |
| rf      | recalibrated     |           0.05 | a1 - a1truth  (effect of the label flip, same rows) | -0.100 +/- 0.053 |  -4.2 |         0.061 |
| rf      | recalibrated     |           0.2  | a1 (benign->malicious, jittered)                    | -0.109 +/- 0.038 |  -6.3 |         0.061 |
| rf      | recalibrated     |           0.2  | a1truth (same rows, true label)                     | +0.014 +/- 0.029 |   1.1 |         0.061 |
| rf      | recalibrated     |           0.2  | s0j (attack->malicious, jittered)                   | -0.002 +/- 0.029 |  -0.2 |         0.061 |
| rf      | recalibrated     |           0.2  | s0 (attack->malicious)                              | +0.079 +/- 0.037 |   4.7 |         0.061 |
| rf      | recalibrated     |           0.2  | a1 - s0j  (label conflict beyond prior shift)       | -0.107 +/- 0.027 |  -8.9 |         0.061 |
| rf      | recalibrated     |           0.2  | a1 - a1truth  (effect of the label flip, same rows) | -0.123 +/- 0.016 | -17.1 |         0.061 |
| xgboost | fixed            |           0.05 | a1 (benign->malicious, jittered)                    | +0.003 +/- 0.015 |   0.5 |         0.02  |
| xgboost | fixed            |           0.05 | a1truth (same rows, true label)                     | -0.018 +/- 0.008 |  -4.7 |         0.02  |
| xgboost | fixed            |           0.05 | s0j (attack->malicious, jittered)                   | -0.003 +/- 0.015 |  -0.4 |         0.02  |
| xgboost | fixed            |           0.05 | s0 (attack->malicious)                              | +0.028 +/- 0.010 |   6   |         0.02  |
| xgboost | fixed            |           0.05 | a1 - s0j  (label conflict beyond prior shift)       | +0.006 +/- 0.017 |   0.8 |         0.02  |
| xgboost | fixed            |           0.05 | a1 - a1truth  (effect of the label flip, same rows) | +0.021 +/- 0.014 |   3.3 |         0.02  |
| xgboost | fixed            |           0.2  | a1 (benign->malicious, jittered)                    | +0.021 +/- 0.010 |   4.7 |         0.02  |
| xgboost | fixed            |           0.2  | a1truth (same rows, true label)                     | -0.014 +/- 0.014 |  -2.3 |         0.02  |
| xgboost | fixed            |           0.2  | s0j (attack->malicious, jittered)                   | +0.020 +/- 0.009 |   5.1 |         0.02  |
| xgboost | fixed            |           0.2  | s0 (attack->malicious)                              | +0.029 +/- 0.011 |   5.7 |         0.02  |
| xgboost | fixed            |           0.2  | a1 - s0j  (label conflict beyond prior shift)       | +0.001 +/- 0.007 |   0.3 |         0.02  |
| xgboost | fixed            |           0.2  | a1 - a1truth  (effect of the label flip, same rows) | +0.035 +/- 0.011 |   6.8 |         0.02  |
| xgboost | recalibrated     |           0.05 | a1 (benign->malicious, jittered)                    | +0.023 +/- 0.042 |   1.2 |         0.04  |
| xgboost | recalibrated     |           0.05 | a1truth (same rows, true label)                     | -0.041 +/- 0.073 |  -1.2 |         0.04  |
| xgboost | recalibrated     |           0.05 | s0j (attack->malicious, jittered)                   | +0.054 +/- 0.029 |   4.2 |         0.04  |
| xgboost | recalibrated     |           0.05 | s0 (attack->malicious)                              | +0.053 +/- 0.021 |   5.6 |         0.04  |
| xgboost | recalibrated     |           0.05 | a1 - s0j  (label conflict beyond prior shift)       | -0.030 +/- 0.030 |  -2.2 |         0.04  |
| xgboost | recalibrated     |           0.05 | a1 - a1truth  (effect of the label flip, same rows) | +0.064 +/- 0.066 |   2.2 |         0.04  |
| xgboost | recalibrated     |           0.2  | a1 (benign->malicious, jittered)                    | +0.017 +/- 0.026 |   1.5 |         0.04  |
| xgboost | recalibrated     |           0.2  | a1truth (same rows, true label)                     | -0.097 +/- 0.066 |  -3.3 |         0.04  |
| xgboost | recalibrated     |           0.2  | s0j (attack->malicious, jittered)                   | +0.049 +/- 0.034 |   3.2 |         0.04  |
| xgboost | recalibrated     |           0.2  | s0 (attack->malicious)                              | +0.084 +/- 0.024 |   7.8 |         0.04  |
| xgboost | recalibrated     |           0.2  | a1 - s0j  (label conflict beyond prior shift)       | -0.032 +/- 0.014 |  -5.2 |         0.04  |
| xgboost | recalibrated     |           0.2  | a1 - a1truth  (effect of the label flip, same rows) | +0.114 +/- 0.076 |   3.3 |         0.04  |

## NEW calibration (twin-free validation rows, tau = 0.1)

| model   | threshold_mode   |   poison_ratio | contrast                                            | delta            |     t |   2sigma_ctrl |
|:--------|:-----------------|---------------:|:----------------------------------------------------|:-----------------|------:|--------------:|
| rf      | fixed            |           0.05 | a1 (benign->malicious, jittered)                    | +0.004 +/- 0.005 |   1.9 |         0.009 |
| rf      | fixed            |           0.05 | a1truth (same rows, true label)                     | -0.005 +/- 0.004 |  -3.2 |         0.009 |
| rf      | fixed            |           0.05 | s0j (attack->malicious, jittered)                   | +0.001 +/- 0.004 |   0.6 |         0.009 |
| rf      | fixed            |           0.05 | s0 (attack->malicious)                              | +0.002 +/- 0.004 |   1   |         0.009 |
| rf      | fixed            |           0.05 | a1 - s0j  (label conflict beyond prior shift)       | +0.003 +/- 0.006 |   1.1 |         0.009 |
| rf      | fixed            |           0.05 | a1 - a1truth  (effect of the label flip, same rows) | +0.010 +/- 0.008 |   2.9 |         0.009 |
| rf      | fixed            |           0.2  | a1 (benign->malicious, jittered)                    | +0.011 +/- 0.001 |  20.2 |         0.009 |
| rf      | fixed            |           0.2  | a1truth (same rows, true label)                     | -0.005 +/- 0.004 |  -2.6 |         0.009 |
| rf      | fixed            |           0.2  | s0j (attack->malicious, jittered)                   | +0.004 +/- 0.004 |   2   |         0.009 |
| rf      | fixed            |           0.2  | s0 (attack->malicious)                              | +0.002 +/- 0.007 |   0.5 |         0.009 |
| rf      | fixed            |           0.2  | a1 - s0j  (label conflict beyond prior shift)       | +0.007 +/- 0.004 |   4.2 |         0.009 |
| rf      | fixed            |           0.2  | a1 - a1truth  (effect of the label flip, same rows) | +0.016 +/- 0.003 |  10.9 |         0.009 |
| rf      | recalibrated     |           0.05 | a1 (benign->malicious, jittered)                    | -0.085 +/- 0.025 |  -7.5 |         0.061 |
| rf      | recalibrated     |           0.05 | a1truth (same rows, true label)                     | +0.015 +/- 0.049 |   0.7 |         0.061 |
| rf      | recalibrated     |           0.05 | s0j (attack->malicious, jittered)                   | -0.003 +/- 0.030 |  -0.2 |         0.061 |
| rf      | recalibrated     |           0.05 | s0 (attack->malicious)                              | +0.058 +/- 0.032 |   4   |         0.061 |
| rf      | recalibrated     |           0.05 | a1 - s0j  (label conflict beyond prior shift)       | -0.083 +/- 0.018 | -10.4 |         0.061 |
| rf      | recalibrated     |           0.05 | a1 - a1truth  (effect of the label flip, same rows) | -0.100 +/- 0.053 |  -4.2 |         0.061 |
| rf      | recalibrated     |           0.2  | a1 (benign->malicious, jittered)                    | -0.109 +/- 0.038 |  -6.3 |         0.061 |
| rf      | recalibrated     |           0.2  | a1truth (same rows, true label)                     | +0.014 +/- 0.029 |   1.1 |         0.061 |
| rf      | recalibrated     |           0.2  | s0j (attack->malicious, jittered)                   | -0.002 +/- 0.029 |  -0.2 |         0.061 |
| rf      | recalibrated     |           0.2  | s0 (attack->malicious)                              | +0.079 +/- 0.037 |   4.7 |         0.061 |
| rf      | recalibrated     |           0.2  | a1 - s0j  (label conflict beyond prior shift)       | -0.107 +/- 0.027 |  -8.9 |         0.061 |
| rf      | recalibrated     |           0.2  | a1 - a1truth  (effect of the label flip, same rows) | -0.123 +/- 0.016 | -17.1 |         0.061 |
| xgboost | fixed            |           0.05 | a1 (benign->malicious, jittered)                    | -0.003 +/- 0.004 |  -1.4 |         0.012 |
| xgboost | fixed            |           0.05 | a1truth (same rows, true label)                     | -0.004 +/- 0.004 |  -2.1 |         0.012 |
| xgboost | fixed            |           0.05 | s0j (attack->malicious, jittered)                   | -0.004 +/- 0.005 |  -1.5 |         0.012 |
| xgboost | fixed            |           0.05 | s0 (attack->malicious)                              | -0.002 +/- 0.005 |  -0.7 |         0.012 |
| xgboost | fixed            |           0.05 | a1 - s0j  (label conflict beyond prior shift)       | +0.001 +/- 0.001 |   1.7 |         0.012 |
| xgboost | fixed            |           0.05 | a1 - a1truth  (effect of the label flip, same rows) | +0.001 +/- 0.003 |   0.9 |         0.012 |
| xgboost | fixed            |           0.2  | a1 (benign->malicious, jittered)                    | -0.003 +/- 0.005 |  -1.3 |         0.012 |
| xgboost | fixed            |           0.2  | a1truth (same rows, true label)                     | -0.005 +/- 0.006 |  -1.9 |         0.012 |
| xgboost | fixed            |           0.2  | s0j (attack->malicious, jittered)                   | -0.005 +/- 0.006 |  -1.9 |         0.012 |
| xgboost | fixed            |           0.2  | s0 (attack->malicious)                              | -0.002 +/- 0.003 |  -1.6 |         0.012 |
| xgboost | fixed            |           0.2  | a1 - s0j  (label conflict beyond prior shift)       | +0.002 +/- 0.002 |   3.1 |         0.012 |
| xgboost | fixed            |           0.2  | a1 - a1truth  (effect of the label flip, same rows) | +0.002 +/- 0.002 |   3   |         0.012 |
| xgboost | recalibrated     |           0.05 | a1 (benign->malicious, jittered)                    | +0.023 +/- 0.042 |   1.2 |         0.04  |
| xgboost | recalibrated     |           0.05 | a1truth (same rows, true label)                     | -0.041 +/- 0.073 |  -1.2 |         0.04  |
| xgboost | recalibrated     |           0.05 | s0j (attack->malicious, jittered)                   | +0.054 +/- 0.029 |   4.2 |         0.04  |
| xgboost | recalibrated     |           0.05 | s0 (attack->malicious)                              | +0.053 +/- 0.021 |   5.6 |         0.04  |
| xgboost | recalibrated     |           0.05 | a1 - s0j  (label conflict beyond prior shift)       | -0.030 +/- 0.030 |  -2.2 |         0.04  |
| xgboost | recalibrated     |           0.05 | a1 - a1truth  (effect of the label flip, same rows) | +0.064 +/- 0.066 |   2.2 |         0.04  |
| xgboost | recalibrated     |           0.2  | a1 (benign->malicious, jittered)                    | +0.017 +/- 0.026 |   1.5 |         0.04  |
| xgboost | recalibrated     |           0.2  | a1truth (same rows, true label)                     | -0.097 +/- 0.066 |  -3.3 |         0.04  |
| xgboost | recalibrated     |           0.2  | s0j (attack->malicious, jittered)                   | +0.049 +/- 0.034 |   3.2 |         0.04  |
| xgboost | recalibrated     |           0.2  | s0 (attack->malicious)                              | +0.084 +/- 0.024 |   7.8 |         0.04  |
| xgboost | recalibrated     |           0.2  | a1 - s0j  (label conflict beyond prior shift)       | -0.032 +/- 0.014 |  -5.2 |         0.04  |
| xgboost | recalibrated     |           0.2  | a1 - a1truth  (effect of the label flip, same rows) | +0.114 +/- 0.076 |   3.3 |         0.04  |
