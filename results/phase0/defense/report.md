# D1 vs generic defenses (CICIDS2017 A1; S0 utility on synthetic and CICIDS)

New calibration (tau = 0.1). Same-seed deltas vs control, final round, 5 seeds. Recovery = share of the undefended damage removed (only where undefended damage exceeds 2 sigma_control).

## 1. A1 at raw benign fidelity: damage and recovery

| model   | threshold_mode   | metric   |   ratio |   2sigma_control | undefended       | D1 (E*=8, g=2)   | D1 (E*=8, g=2) recovery   | loss filter      | loss filter recovery   | kNN sanitize     | kNN sanitize recovery   |
|:--------|:-----------------|:---------|--------:|-----------------:|:-----------------|:-----------------|:--------------------------|:-----------------|:-----------------------|:-----------------|:------------------------|
| rf      | fixed            | FPR rise |    0.05 |            0.009 | +0.009 +/- 0.006 | -0.000 +/- 0.004 |                           | +0.005 +/- 0.004 |                        | +0.001 +/- 0.004 |                         |
| rf      | fixed            | FPR rise |    0.1  |            0.009 | +0.025 +/- 0.005 | -0.002 +/- 0.002 | 106%                      | +0.027 +/- 0.013 | -10%                   | +0.001 +/- 0.004 | 96%                     |
| rf      | fixed            | FPR rise |    0.2  |            0.009 | +0.337 +/- 0.139 | +0.003 +/- 0.006 | 99%                       | +0.329 +/- 0.143 | 2%                     | -0.000 +/- 0.006 | 100%                    |
| rf      | fixed            | FPR rise |    0.5  |            0.009 | +0.880 +/- 0.024 | +0.067 +/- 0.009 | 92%                       | +0.880 +/- 0.026 | 0%                     | +0.004 +/- 0.008 | 99%                     |
| rf      | recalibrated     | TPR drop |    0.05 |            0.061 | +0.034 +/- 0.050 | +0.003 +/- 0.034 |                           | +0.010 +/- 0.025 |                        | -0.007 +/- 0.008 |                         |
| rf      | recalibrated     | TPR drop |    0.1  |            0.061 | +0.060 +/- 0.035 | -0.009 +/- 0.019 |                           | +0.047 +/- 0.023 |                        | +0.017 +/- 0.051 |                         |
| rf      | recalibrated     | TPR drop |    0.2  |            0.061 | +0.140 +/- 0.015 | +0.029 +/- 0.029 | 79%                       | +0.135 +/- 0.029 | 3%                     | +0.015 +/- 0.076 | 89%                     |
| rf      | recalibrated     | TPR drop |    0.5  |            0.061 | +0.282 +/- 0.038 | +0.036 +/- 0.037 | 87%                       | +0.289 +/- 0.035 | -2%                    | +0.087 +/- 0.128 | 69%                     |
| xgboost | fixed            | FPR rise |    0.05 |            0.012 | +0.005 +/- 0.007 | -0.003 +/- 0.004 |                           | +0.001 +/- 0.003 |                        | +0.003 +/- 0.003 |                         |
| xgboost | fixed            | FPR rise |    0.1  |            0.012 | +0.014 +/- 0.023 | -0.004 +/- 0.005 | 126%                      | +0.012 +/- 0.016 | 18%                    | +0.003 +/- 0.004 | 77%                     |
| xgboost | fixed            | FPR rise |    0.2  |            0.012 | +0.279 +/- 0.374 | -0.001 +/- 0.002 | 100%                      | +0.282 +/- 0.379 | -1%                    | +0.003 +/- 0.002 | 99%                     |
| xgboost | fixed            | FPR rise |    0.5  |            0.012 | +0.563 +/- 0.457 | +0.040 +/- 0.043 | 93%                       | +0.566 +/- 0.455 | -0%                    | +0.006 +/- 0.002 | 99%                     |
| xgboost | fixed            | FPR rise |    0.8  |            0.012 | +0.923 +/- 0.058 | +0.095 +/- 0.046 | 90%                       |                  |                        |                  |                         |
| xgboost | fixed            | FPR rise |    0.9  |            0.012 | +0.965 +/- 0.005 | +0.132 +/- 0.036 | 86%                       |                  |                        |                  |                         |
| xgboost | recalibrated     | TPR drop |    0.05 |            0.04  | -0.001 +/- 0.019 | -0.025 +/- 0.044 |                           | -0.020 +/- 0.030 |                        | -0.009 +/- 0.017 |                         |
| xgboost | recalibrated     | TPR drop |    0.1  |            0.04  | +0.009 +/- 0.040 | -0.010 +/- 0.031 |                           | +0.000 +/- 0.019 |                        | +0.007 +/- 0.017 |                         |
| xgboost | recalibrated     | TPR drop |    0.2  |            0.04  | +0.060 +/- 0.052 | -0.022 +/- 0.023 | 137%                      | +0.054 +/- 0.039 | 11%                    | -0.001 +/- 0.006 | 101%                    |
| xgboost | recalibrated     | TPR drop |    0.5  |            0.04  | +0.219 +/- 0.058 | +0.009 +/- 0.020 | 96%                       | +0.207 +/- 0.053 | 5%                     | -0.000 +/- 0.019 | 100%                    |
| xgboost | recalibrated     | TPR drop |    0.8  |            0.04  | +0.415 +/- 0.027 | +0.159 +/- 0.037 | 62%                       |                  |                        |                  |                         |
| xgboost | recalibrated     | TPR drop |    0.9  |            0.04  | +0.520 +/- 0.023 | +0.162 +/- 0.034 | 69%                       |                  |                        |                  |                         |

## 2. Overhead (mean seconds per round over rounds with honeypot data)

| model   | defense   |   defense_s_per_round |   fit_s_per_round |   defense_overhead_vs_fit |
|:--------|:----------|----------------------:|------------------:|--------------------------:|
| rf      | d1_E8_g2  |                0.0001 |            1.9115 |                    0.0001 |
| rf      | knn       |                0.069  |            1.6172 |                    0.0427 |
| rf      | loss      |                0.6752 |            2.2741 |                    0.2969 |
| rf      | none      |                0      |            2.2902 |                    0      |
| xgboost | d1_E8_g2  |                0.0001 |            1.1758 |                    0.0001 |
| xgboost | knn       |                0.0672 |            1.0578 |                    0.0635 |
| xgboost | loss      |                0.6757 |            1.2039 |                    0.5612 |
| xgboost | none      |                0      |            1.2204 |                    0      |

## 3. Utility: what each defense costs the honest loop (S0, fixed threshold, final round)

`*_gain_retained` = share of the undefended S0 TPR gain over control that survives the defense.

| dataset    | model   |   ratio | defense        |    fpr |   mean_hp_weight |   tpr_seen_both |   control_seen_both |   tpr_seed_only |   control_seed_only |   tpr_honeypot_only |   control_honeypot_only | seen_both_gain_retained   | honeypot_only_gain_retained   |
|:-----------|:--------|--------:|:---------------|-------:|-----------------:|----------------:|--------------------:|----------------:|--------------------:|--------------------:|------------------------:|:--------------------------|:------------------------------|
| synthetic  | rf      |    0.05 | undefended     | 0.0109 |          nan     |           0.953 |               0.946 |           0.998 |               0.998 |               0.982 |                   0.39  |                           | 100%                          |
| synthetic  | rf      |    0.05 | D1 (E*=8, g=2) | 0.0082 |            0.101 |           0.944 |               0.946 |           0.998 |               0.998 |               0.461 |                   0.39  |                           | 12%                           |
| synthetic  | rf      |    0.05 | loss filter    | 0.0105 |            0.986 |           0.952 |               0.946 |           0.996 |               0.998 |               0.978 |                   0.39  |                           | 99%                           |
| synthetic  | rf      |    0.05 | kNN sanitize   | 0.0086 |            0.597 |           0.947 |               0.946 |           0.997 |               0.998 |               0.657 |                   0.39  |                           | 45%                           |
| synthetic  | rf      |    0.2  | undefended     | 0.0161 |          nan     |           0.961 |               0.946 |           0.997 |               0.998 |               0.997 |                   0.39  |                           | 100%                          |
| synthetic  | rf      |    0.2  | D1 (E*=8, g=2) | 0.0087 |            0.1   |           0.947 |               0.946 |           0.998 |               0.998 |               0.664 |                   0.39  |                           | 45%                           |
| synthetic  | rf      |    0.2  | loss filter    | 0.016  |            0.99  |           0.961 |               0.946 |           0.998 |               0.998 |               0.997 |                   0.39  |                           | 100%                          |
| synthetic  | rf      |    0.2  | kNN sanitize   | 0.0106 |            0.6   |           0.953 |               0.946 |           0.997 |               0.998 |               0.839 |                   0.39  |                           | 74%                           |
| synthetic  | xgboost |    0.05 | undefended     | 0.0107 |          nan     |           0.955 |               0.95  |           0.996 |               0.996 |               0.984 |                   0.341 |                           | 100%                          |
| synthetic  | xgboost |    0.05 | D1 (E*=8, g=2) | 0.0086 |            0.101 |           0.951 |               0.95  |           0.996 |               0.996 |               0.406 |                   0.341 |                           | 10%                           |
| synthetic  | xgboost |    0.05 | loss filter    | 0.0103 |            0.986 |           0.954 |               0.95  |           0.995 |               0.996 |               0.983 |                   0.341 |                           | 100%                          |
| synthetic  | xgboost |    0.05 | kNN sanitize   | 0.0089 |            0.597 |           0.952 |               0.95  |           0.996 |               0.996 |               0.613 |                   0.341 |                           | 42%                           |
| synthetic  | xgboost |    0.2  | undefended     | 0.0139 |          nan     |           0.963 |               0.95  |           0.997 |               0.996 |               0.994 |                   0.341 |                           | 100%                          |
| synthetic  | xgboost |    0.2  | D1 (E*=8, g=2) | 0.0089 |            0.1   |           0.953 |               0.95  |           0.997 |               0.996 |               0.72  |                   0.341 |                           | 58%                           |
| synthetic  | xgboost |    0.2  | loss filter    | 0.0135 |            0.99  |           0.963 |               0.95  |           0.997 |               0.996 |               0.994 |                   0.341 |                           | 100%                          |
| synthetic  | xgboost |    0.2  | kNN sanitize   | 0.0094 |            0.6   |           0.954 |               0.95  |           0.995 |               0.996 |               0.853 |                   0.341 |                           | 78%                           |
| CICIDS2017 | rf      |    0.05 | undefended     | 0.0102 |            1     |           0.806 |               0.798 |           0.995 |               0.995 |               0.81  |                   0.619 |                           | 100%                          |
| CICIDS2017 | rf      |    0.05 | D1 (E*=8, g=2) | 0.0076 |            0.84  |           0.801 |               0.798 |           0.995 |               0.995 |               0.744 |                   0.619 |                           | 65%                           |
| CICIDS2017 | rf      |    0.05 | loss filter    | 0.0091 |            0.993 |           0.807 |               0.798 |           0.995 |               0.995 |               0.794 |                   0.619 |                           | 92%                           |
| CICIDS2017 | rf      |    0.05 | kNN sanitize   | 0.006  |            0.513 |           0.797 |               0.798 |           0.995 |               0.995 |               0.744 |                   0.619 |                           | 65%                           |
| CICIDS2017 | rf      |    0.2  | undefended     | 0.0103 |            1     |           0.817 |               0.798 |           0.995 |               0.995 |               0.865 |                   0.619 |                           | 100%                          |
| CICIDS2017 | rf      |    0.2  | D1 (E*=8, g=2) | 0.0071 |            0.833 |           0.802 |               0.798 |           0.995 |               0.995 |               0.747 |                   0.619 |                           | 52%                           |
| CICIDS2017 | rf      |    0.2  | loss filter    | 0.0081 |            0.998 |           0.817 |               0.798 |           0.995 |               0.995 |               0.864 |                   0.619 |                           | 100%                          |
| CICIDS2017 | rf      |    0.2  | kNN sanitize   | 0.0054 |            0.512 |           0.807 |               0.798 |           0.995 |               0.995 |               0.745 |                   0.619 |                           | 51%                           |
| CICIDS2017 | xgboost |    0.05 | undefended     | 0.0052 |            1     |           0.788 |               0.79  |           0.994 |               0.995 |               0.773 |                   0.599 |                           | 100%                          |
| CICIDS2017 | xgboost |    0.05 | D1 (E*=8, g=2) | 0.0035 |            0.84  |           0.772 |               0.79  |           0.994 |               0.995 |               0.743 |                   0.599 |                           | 83%                           |
| CICIDS2017 | xgboost |    0.05 | loss filter    | 0.0038 |            0.993 |           0.784 |               0.79  |           0.994 |               0.995 |               0.769 |                   0.599 |                           | 98%                           |
| CICIDS2017 | xgboost |    0.05 | kNN sanitize   | 0.0046 |            0.513 |           0.784 |               0.79  |           0.994 |               0.995 |               0.743 |                   0.599 |                           | 83%                           |
| CICIDS2017 | xgboost |    0.2  | undefended     | 0.0047 |            1     |           0.8   |               0.79  |           0.994 |               0.995 |               0.824 |                   0.599 |                           | 100%                          |
| CICIDS2017 | xgboost |    0.2  | D1 (E*=8, g=2) | 0.0074 |            0.833 |           0.774 |               0.79  |           0.994 |               0.995 |               0.747 |                   0.599 |                           | 66%                           |
| CICIDS2017 | xgboost |    0.2  | loss filter    | 0.0052 |            0.998 |           0.8   |               0.79  |           0.994 |               0.995 |               0.818 |                   0.599 |                           | 97%                           |
| CICIDS2017 | xgboost |    0.2  | kNN sanitize   | 0.0026 |            0.512 |           0.788 |               0.79  |           0.994 |               0.995 |               0.747 |                   0.599 |                           | 66%                           |

## 4. What D1 does to the poison's weight (A1, jitter 0)

| model   |   target_poison_ratio |   mean_weight |   zero_weight_frac |   effective_ratio |   nominal_ratio |
|:--------|----------------------:|--------------:|-------------------:|------------------:|----------------:|
| rf      |                  0.05 |        0.2301 |                  0 |            0.012  |            0.05 |
| rf      |                  0.1  |        0.2295 |                  0 |            0.0249 |            0.1  |
| rf      |                  0.2  |        0.2289 |                  0 |            0.0541 |            0.2  |
| rf      |                  0.5  |        0.2307 |                  0 |            0.1875 |            0.5  |
| xgboost |                  0.05 |        0.2301 |                  0 |            0.012  |            0.05 |
| xgboost |                  0.1  |        0.2295 |                  0 |            0.0249 |            0.1  |
| xgboost |                  0.2  |        0.2289 |                  0 |            0.0541 |            0.2  |
| xgboost |                  0.5  |        0.2307 |                  0 |            0.1875 |            0.5  |
| xgboost |                  0.8  |        0.2302 |                  0 |            0.4794 |            0.8  |
| xgboost |                  0.9  |        0.2299 |                  0 |            0.6741 |            0.9  |

## 5. Attacker cost to reach the same damage (fixed-threshold FPR rise >= 0.1)

`_x` = D1 cost / undefended cost; `>` = not reached at the largest tested ratio (a lower bound).

| model   |   target_FPR_rise |   undefended_first_ratio |   D1_first_ratio |   D1_max_ratio_tested |   D1_max_FPR_rise |   cum_flows_undef | cum_flows_D1   | cum_flows_x   |   cum_packets_undef | cum_packets_D1   | cum_packets_x     |   cum_bytes_undef | cum_bytes_D1   | cum_bytes_x       |   cum_duration_s_undef | cum_duration_s_D1   | cum_duration_s_x   |
|:--------|------------------:|-------------------------:|-----------------:|----------------------:|------------------:|------------------:|:---------------|:--------------|--------------------:|:-----------------|:------------------|------------------:|:---------------|:------------------|-----------------------:|:--------------------|:-------------------|
| rf      |               0.1 |                      0.2 |            nan   |                   0.5 |             0.067 |              7500 | >3e+04         | >4.0          |              149313 | >5.8e+05         | >3.9              |       8.48896e+07 | >3.21e+08      | >3.8              |                 131937 | >5.34e+05           | >4.0               |
| xgboost |               0.1 |                      0.2 |              0.9 |                   0.9 |             0.132 |              7500 | 270000.0       | 36.0          |              149313 | 5178989.0        | 34.68535978686441 |       8.48896e+07 | 2839830487.0   | 33.45322278701544 |                 131937 | 4779333.086743999   | 36.22435324872668  |

## 6. Sensitivity to the parameterisation (XGBoost, ratio 0.5, jitter 0)

2 sigma_control = 0.012. Pre-registered criterion (DECISIONS 20): 'not sensitive' iff FPR damage stays within 2 sigma over E* >= 4, gamma >= 1. **Criterion met: False** (2/12 configurations in the region).

|   E_star |   gamma | components   |   delta_fpr_mean |   delta_fpr_sd |   n_seeds | within_2sigma   |
|---------:|--------:|:-------------|-----------------:|---------------:|----------:|:----------------|
|        2 |       1 | all          |           0.3403 |         0.4354 |         5 | False           |
|        2 |       2 | all          |           0.084  |         0.0873 |         5 | False           |
|        2 |       3 | all          |           0.0757 |         0.0778 |         5 | False           |
|        4 |       1 | all          |           0.0813 |         0.0901 |         5 | False           |
|        4 |       2 | all          |           0.0599 |         0.0637 |         5 | False           |
|        4 |       3 | all          |           0.0594 |         0.062  |         5 | False           |
|        8 |       1 | all          |           0.0529 |         0.0594 |         5 | False           |
|        8 |       2 | all          |           0.0402 |         0.0429 |         5 | False           |
|        8 |       2 | bytes        |           0.0492 |         0.0514 |         5 | False           |
|        8 |       2 | depth        |           0.0153 |         0.0166 |         5 | False           |
|        8 |       2 | duration_s   |           0.0659 |         0.0691 |         5 | False           |
|        8 |       2 | packets      |           0.0105 |         0.0105 |         5 | True            |
|        8 |       3 | all          |           0.0358 |         0.0379 |         5 | False           |
|       16 |       1 | all          |           0.0297 |         0.0317 |         5 | False           |
|       16 |       2 | all          |           0.0246 |         0.0254 |         5 | False           |
|       16 |       3 | all          |           0.0197 |         0.0204 |         5 | False           |
|       32 |       1 | all          |           0.0151 |         0.0175 |         5 | False           |
|       32 |       2 | all          |           0.005  |         0.0059 |         5 | True            |
|       32 |       3 | all          |           0.0034 |         0.0039 |         5 | True            |

## 7. The adversary's move: pad the flows to buy weight (XGBoost, ratio 0.5)

| defense        |   cost_padding |   realized_nn_median |   mean_hp_weight |   effective_ratio | delta_fpr        |   attacker_bytes |   attacker_duration_s |
|:---------------|---------------:|---------------------:|-----------------:|------------------:|:-----------------|-----------------:|----------------------:|
| D1 (E*=8, g=2) |              1 |             nan      |           0.2307 |            0.1875 | +0.040 +/- 0.043 |      3.21351e+08 |      534067           |
| D1 (E*=8, g=2) |              2 |               0.1352 |           0.3106 |            0.237  | +0.007 +/- 0.004 |      6.42701e+08 |           1.06813e+06 |
| D1 (E*=8, g=2) |              8 |               0.3306 |           0.4758 |            0.3224 | -0.001 +/- 0.004 |      2.57081e+09 |           4.27254e+06 |
| D1 (E*=8, g=2) |             32 |               0.5322 |           0.8984 |            0.4732 | -0.004 +/- 0.005 |      1.02832e+10 |           1.70901e+07 |
| undefended     |              1 |               0.0108 |           1      |            0.5    | +0.563 +/- 0.457 |      3.21351e+08 |      534067           |
| undefended     |              2 |               0.1352 |           1      |            0.5    | +0.021 +/- 0.020 |      6.42701e+08 |           1.06813e+06 |
| undefended     |              8 |               0.3306 |           1      |            0.5    | -0.003 +/- 0.006 |      2.57081e+09 |           4.27254e+06 |
| undefended     |             32 |               0.5322 |           1      |            0.5    | -0.005 +/- 0.005 |      1.02832e+10 |           1.70901e+07 |
