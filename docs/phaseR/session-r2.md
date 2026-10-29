# Phase R session: R2 ShareCap generality

Read `docs/phaseR/common.md` first, then do item **R2** from `docs/DECISIONS.md` §31.2 (R2.1,
R2.3, R2.4; R2.2's code already exists and is unit-tested).

## Setup

Data and caches per `common.md` §2. R2 needs three datasets:

```
python -m experiments.phase0_loop_data --source cicids
python -m experiments.phase0_loop_data --source cicids-fixed
python -m experiments.phase0_loop_data --source unsw-nb15
```

## Run

One script, one dataset per invocation, run in this order. Each one must finish before the next
starts; never run two at once on this VM.

```
mkdir -p results/phaseR/r2
nohup bash experiments/run_phaseR_r2.sh cicids       > results/phaseR/r2/run_cicids.log 2>&1 &
# when "R2 runs complete for cicids" appears in that log:
nohup bash experiments/run_phaseR_r2.sh cicids-fixed > results/phaseR/r2/run_cicids-fixed.log 2>&1 &
# then:
nohup bash experiments/run_phaseR_r2.sh unsw-nb15    > results/phaseR/r2/run_unsw-nb15.log 2>&1 &
```

What each runs (`experiments/run_phaseR_r2.sh` is the source of truth; 15 seeds throughout;
tau 0.1 on `cicids`, 0 on the other two, as §31 fixes):

| dataset | models | families | jobs |
|---|---|---|---:|
| `cicids` | RF, XGBoost, logreg, MLP | R2.1 (control; A1 at ratios 0.2/0.5/0.9, jitter 0; S0 at 0.2; each under none / ShareCap 0.02, 0.05, 0.1, 0.2 / uniform 0.05) | 1,500 |
| `cicids` | RF, XGBoost | R2.3 (`--defense srcpart --sp-alpha 0.5`, same A1 and S0 arms) | 120 |
| `cicids` | RF, XGBoost | R2.4 (`s0crowd`, filler factor 1/4/9, under none / ShareCap 0.05, two fillers: **primary** stale replay of seed_train's DDoS rows, **secondary** benign at jitter 0.7; §31.6) | 360 |
| `cicids-fixed` | RF, XGBoost | R2.1 | 750 |
| `unsw-nb15` | RF, XGBoost | R2.1 | 750 |

All jobs for a dataset land in `results/phaseR/r2/<dataset>/jobs/`. The defense is part of each
job key (`_sharecap_c0.05`, `_uniform_w0.05`, `_srcpart_a0.5`, none = no suffix), as are the
crowd factor and filler (`_cf4_cstaleDDoS` for the stale replay, `_cf4_cj0.7` for the benign
filler). The stale filler reads `seed_family` from the loop cache: a cache built before §31.6
lacks it, and the runner then refuses to start, so build the cache with the current code. R2.4's m = 0 reference is R2.1's own `s0` runs under `none` and
`sharecap_c0.05`, which is why R2.4 adds only the crowd arms. Ratio 0.9 on UNSW-NB15 exhausts the
benign pool, so expect `batch_resampled = True` in those rows. That is allowed and reported
(§31.2). Commit and push after each invocation finishes.

The MLP at ratio 0.9 is the slowest job type in this project. On a small VM, `cicids` can take
most of a day. That is expected, not a hang.

## Statistics

`experiments/phaseR_r2_stats.py` (yours to write; import the machinery from
`experiments/phase0_stats_recompute.py`). Per pair (dataset, model), all from final-round rows,
paired by seed against the pair's control:

- **R2.1.** $R$ (fixed-threshold $\Delta$FPR, A1 ratio 0.5) and $U$ (S0 gain on
  `tpr_honeypot_only` for `cicids` / `cicids-fixed`; on overall `tpr` for `unsw-nb15`) for every
  defense, exactly as §31.2 defines them. The 15-cell Holm family (defended minus undefended FPR).
  The two evaluability checks, then the verdict. The cap curve (every $c$, every ratio) as a
  table, no bar. Seed-bootstrap CIs as §31.2 names them.
- **R2.3.** $R$ and $U$ for `srcpart_a0.5` next to ShareCap 0.05 on CICIDS2017 RF / XGBoost, and
  the dominance statement §31.2 asks for.
- **R2.4** (as amended by §31.6). Per (model, filler), the 6-cell loss family (Holm),
  $\ell(9, c{=}0.05)$ against $0.5\,g(\mathrm{S0}, c{=}0.05)$, the dilution-attributable
  difference, and fixed-threshold FPR for every crowd arm. **The verdict is read on the stale
  filler**; the benign filler's bar outcome is reported next to it as secondary. For stale arms,
  also report `tpr_seed_only` (DDoS).

## Write up

`docs/phaseR/r2-results.md`: branch name, one section per pair (8 pairs) with its R2.1 verdict,
then R2.3, then R2.4, then the `common.md` §6 table. Commit, push, stop.

## Smoke-tested

All three invocations ran to completion at `--seeds 1 --rounds 2`
(`SMOKE=1 ROOT=.smoke/phaseR bash experiments/run_phaseR_r2.sh <dataset>`) before §31 was
committed, including every defense, `srcpart`, and `s0crowd`. The `cicids` invocation was
smoke-tested again after the §31.6 addendum, with both crowd fillers.
