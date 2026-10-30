# Phase B.4 — honeypot realism (DECISIONS §33)

Confirmatory run of the §33 pre-registration: does a **realistic** honeypot let
real-traffic A1 reproduce the feature-space poisoning that §32 (low-interaction)
could not? Two conditions, same scaled protocol, 15 seeds, RF+XGBoost, ratios 0.2
and 0.5, fixed and recalibrated thresholds, s28 null arms, ShareCap c=0.05.

- **(L) low-interaction:** Cowrie (SSH) + Flask HTTP honeypot — the §32 decoys.
- **(H) high-interaction clone:** the *same nginx image/config/content as prod-web*
  and a *real OpenSSH configured like prod-ssh*, on the production ports, logging only.

## Literal verdict

**§33 bar — "realism drives poisoning": HOLDS.**

| half of the bar | H (high-interaction) | L (low-interaction) |
|---|---|---|
| replay fidelity ≤ 3× floor | **0.95× ✓** | 46.3× ✗ |
| RF fixed ΔFPR r=0.5 clears Holm + null-rule | **+0.620, clears ✓** | +0.0002, does not clear ✗ |
| meets both? | **yes** | no (neither) |

H meets both halves; L meets neither → by §33's definition (*"holds iff under (H)
both … while under (L) it does not"*), the bar **holds**.

## 1. Exploratory diagnosis (existing §32 data) — what the §33 run then tested

The §32 mimic→benign NN distance, decomposed by feature group
(`results/phaseB/diag_feature_groups.csv`; **exploratory**):

| group | share of squared distance |
|---|---:|
| timing / IAT | ~48% |
| backward / server-produced | ~23% |
| derived (rates, ratios) | ~18% |
| forward / client-controlled | ~10% |
| flags | ~0.4% |

Timing (~48%) and server-produced bytes (~23%) dominate; the client-controlled
(forward) features the attacker fully determines are only ~10%. **This is a
hypothesis, not a confirmation**: it *suggested* the limit was the honeypot's server
half (its software, headers and response timing), and §33 was designed to test it.
The low-interaction server differed from production exactly there — `Server:
gunicorn` vs `nginx/1.27.5`, Flask ETags, Flask response timing — while the feature
set itself carries **no** port/IP or other honeypot-identifying field (the 24
canonical features are flow statistics only; the HTTP mimic hits port 80 on both
decoy and prod). The §33 result below **confirms the hypothesis**: making the server
realistic closed the gap and enabled the damage.

## 2. B.1 — fidelity, matched reference, twin fraction for every condition

`results/phaseB/b1_fidelity_{L,H}.csv`. Median NN RMS distance of the honeypot-bound
mimic flows to the defender benign reference, with the benign floor at matched
reference size and the ratio; **twin fraction (δ=0.0015) reported alongside**.

| condition | strategy | median NN | ratio to floor | twin fraction |
|---|---|---:|---:|---:|
| L | replay | 0.789 | 46.3× | 0.0 |
| L | oracle | 0.786 | 46.1× | 0.0 |
| **H** | **replay** | **0.0211** | **0.95×** | **0.00047** |
| H | oracle | 0.0216 | 0.98× | 0.00047 |
| — | paper, copy fidelity (§17/§26) | — | ~1× | **0.11** |

The high-interaction clone collapses the fidelity gap from **46× to ~1×** the benign
floor — the mimic flows now sit essentially *on* the benign cluster. **But note the
twin fraction:** H reaches ~0.0005, still **~200× below the paper's copy-fidelity
0.11**. So H matches benign-cluster *density* (median NN ≈ floor) without reaching
the paper's near-exact-duplicate *tail*. The paper's FPR collapse tracked twin
fraction; that H produces a large ΔFPR (below) at twin fraction 0.0005 says the
damage sets in once the mimic reaches the benign cluster, not only at the extreme
twin density — a finding worth stating, since it means real traffic need not reach
0.11 twins to be dangerous.

## 3. B.2 — damage (fixed ΔFPR r=0.5 Holm family, RF primary; `b4_stats.csv`)

| condition | arm | mean ΔFPR | 95% CI | clears Holm | CI incl. 0 |
|---|---|---:|---|:--:|:--:|
| **H** | a1 | **+0.6204** | [0.392, 0.849] | ✓ | — |
| H | a1truth | +0.00003 | [−0.00003, 0.00009] | — | ✓ |
| H | junk | +0.0409 | [−0.042, 0.124] | — | ✓ |
| L | a1 | +0.00020 | [0.00013, 0.00027] | ✓ | — |
| L | a1truth | −0.00015 | [−0.00024, −0.00006] | — | ✗ |
| L | junk | +0.00016 | [0.00009, 0.00023] | ✓ | — |

- **H:** a1 raises FPR by **+0.62**, clears Holm; both null arms' CIs include 0 →
  **a1 clears Holm + null-rule**. Recalibrated ΔTPR r=0.5 is **−0.036** (RF) /
  −0.017 (XGB) — the TPR collapse too. XGBoost a1 ΔFPR is +0.275 (p_t=0.029, does
  not clear Holm's 0.0167 step); RF is the §33 primary model and clears.
- **L:** a1 is at the **noise floor (+0.0002)**, junk moves the *same* amount and
  also "clears" Holm, and a1truth's CI excludes 0 — so the null-arm rule **fails**
  and nothing A1-specific survives. L does not clear.

So **realism takes real-traffic A1 from +0.0002 (L) to +0.62 (H)** — the
feature-space catastrophe, reproduced end to end through a live honeypot and the
pinned CICFlowMeter, once the honeypot's server half is realistic.

**ShareCap c=0.05 (RF, fixed ΔFPR):** under H it recovers **R=0.98** (r=0.2) and
**R=0.996** (r=0.5) — the paper's defense neutralises the real-traffic damage
(undefended +0.62 → defended +0.003). Under L there is no damage to recover
(R ill-defined against the +0.0002 noise floor).

## 4. Matched-counts check (H vs L, as §33 requires)

L was captured to **at least** H's totals for the quantities that drive the data:

| count | H | L | ≥ H? |
|---|---:|---:|:--:|
| benign flows | 79,080 | 88,969 | ✓ |
| replay mimic (the bar strategy) | 6,381 | 7,194 | ✓ |
| eval attack rows (of 3,802 / 12,798 total) | ~1,520 | ~5,119 | ✓ |
| oracle mimic (secondary, **not** in the bar) | 12,724 | 9,737 | ✗ (77%) |

Benign, the bar strategy (replay) and attack rows all meet or exceed H. The one
shortfall is the **oracle** secondary strategy (9,737 vs 12,724); it is not used in
the §33 bar (replay is), and both L mimic strategies sit at ~46× regardless, so it
does not affect the verdict. Flagged, not hidden.

## 5. Does the attacker's benign capture share the defender's scripts? (asked explicitly)

**Yes.** The attacker's "own benign capture" — the source of both the **replay** and
**profile** strategies — is produced by `attack.py benign` / `replay`, which browse
the **same nine `SITE_PATHS`** with the **same fresh-connection pattern and
near-identical think-times** as the defender's `benign-client` (`dense_web_session`).
The two benign generators are the same process in all but name.

**Consequence, stated plainly:** under H, **replay and profile are not independent
attacker knowledge** — they are close to the **oracle** (defender-data) strategy.
B.4's finding is therefore "a realistic honeypot lets real-traffic A1 reproduce the
feature-space damage **given an attacker whose benign model already matches the
defender's**." It does **not** establish that an attacker with a *different* benign
model would succeed. That is the open question, pre-registered (not run) as
**DECISIONS §34 (Phase B.5)**: the attacker's benign traffic from a *different*
generator — different browsing paths, SSH command mix, and timing distribution —
against the same high-interaction honeypot, with the same bar.

## Deviations (none affect the results; memory/speed only)

- **Loop workers 3→2→1.** The §33 commands said `--workers 2`; some B.2 loops ran at
  1 worker after repeated OOM-kills (see below). Worker count changes only speed and
  float-reduction order within a model's own fixed seed — not the per-seed results.
- **L captured in 4 short segments** with `wsl --shutdown` between each (and a one-off
  kill of orphaned worker processes), because condition L's Cowrie+Flask Docker VM
  balloons to the ~1.86 GB VM ceiling; H's lighter nginx clones did not. Segmentation
  changes only when memory is reclaimed, not the captured traffic (ground truth and
  pcaps accumulate across segments; counts above exceed H).
- **Oracle mimic count** in L is 77% of H's (secondary strategy, not in the bar).

## Peak memory

The two-condition run repeatedly approached and crossed the 90% line and was paused
and resumed per instruction. Observed peaks: **~93%** during L's capture (the Cowrie
+ Flask Docker VM at its ~1.86 GB ceiling), and **~96–97%** transiently when
OOM-killed B.2 loops left orphaned worker processes (cleared, after which the loops
completed at 1 worker ~74–85%). H's capture ran at ~80%. The whole pipeline stayed
within the 1.86 GB Docker VM by splitting inputs; no memory limit was raised.

## B.5 — independent attacker benign knowledge (DECISIONS §34)

B.4's replay/profile mimics were learned from the attacker's own benign capture,
which (§5 above) used the *same* scripts/paths/timing as the defender — so B.4-H
was close to oracle knowledge. B.5 removes that: the attacker's benign generator is
**independent** (`ATTACKER_INDEP=1`) — a different URL set (query strings, deeper
and 404-prone paths: `INDEP_PATHS`) and a heavy-tailed (Pareto) think-time
distribution, vs the defender's nine `SITE_PATHS` and near-uniform small gaps. Same
high-interaction honeypot (condition H clone), same §32 damage protocol, replay +
profile strategies (no oracle), `--workers 2`. Counts: benign 84,207, replay mimic
6,449, attack 3,802 (~1,520 eval) — matched to H.

**Fidelity (independent attacker):**

| strategy | median NN | ratio to floor | twin fraction |
|---|---:|---:|---:|
| replay | 0.0205 | **0.93×** | 0.00047 |
| profile | 0.0210 | 0.95× | 0.00077 |

The independent attacker **still reaches the benign cluster** (~0.93× floor) —
because the fidelity is dominated by the honeypot's server half (timing + backward
bytes, §1), which a realistic honeypot supplies regardless of which paths the
attacker browses. Different benign scripts do not move it out of the cluster.

**Damage (RF, fixed ΔFPR r=0.5; `b5_stats.csv`):**

| arm | mean ΔFPR | 95% CI | clears Holm | CI incl. 0 |
|---|---:|---|:--:|:--:|
| a1 | **+0.458** | [0.235, 0.681] | ✓ | — |
| a1truth | −0.00010 | [−0.00015, −0.00005] | — | ✗ |
| junk | +0.028 | [−0.025, 0.082] | — | ✓ |

a1 raises FPR by **+0.458** (XGBoost +0.415, both clear Holm); recalibrated ΔTPR is
**−0.046**. ShareCap c=0.05 recovers **R=0.98** (undefended +0.458 → defended +0.010).

**Literal §34 verdict: DOES NOT HOLD.** The bar requires the replay fidelity within
3× the floor (met: 0.93×) **and** a1 to clear Holm with the s28 null-arm rule (each
null's 95% CI includes 0). a1truth's CI is [−0.00015, −0.00005] — it **excludes 0**,
so the null-arm rule fails and the bar is not met as written.

**Interpretation.** The failure is a **bar technicality, not a null result for A1.**
a1truth here is −0.0001 — a negligible effect in the *safe* direction (labelling the
mimic flows correctly benign slightly *lowers* FPR), with a CI so tight (sd 1e-4)
that it excludes 0. a1's +0.458 dwarfs both nulls by ~4,000×. So A1 **does** inflict
large, real damage with independent benign knowledge — B.5 essentially **replicates
B.4-H** (+0.458 vs +0.62). The substantive conclusion: **the honeypot's realism, not
a benign model shared with the defender, is what drives the poisoning** — which
resolves the B.4 confound in §5. The s28 "CI includes 0" null-arm rule is too strict
for a null that lands at a trivially non-zero value in the safe direction; a
magnitude-aware rule (e.g. |null mean| < a small fraction of the a1 effect) would
pass here, and is worth adopting for the paper. Reported as the literal verdict with
this interpretation, per the pre-registration discipline — not re-scored.

## Reading fidelity: ratio to the benign floor, not absolute twin fraction

Across the whole paper, mimic fidelity should be read as the **ratio of the mimic's
median NN distance to the benign-to-benign floor at matched reference size**, not as
the absolute twin fraction (δ=0.0015):

| condition | twin fraction | ratio to floor | A1 ΔFPR r=0.5 |
|---|---:|---:|---:|
| L (low-interaction) | 0.0 | 46× | +0.0002 (none) |
| H (high-interaction, matched benign) | 0.0005 | 0.95× | +0.62 |
| H5 (high-interaction, independent benign) | 0.00047 | 0.93× | +0.458 |
| paper, copy fidelity (§17/§26) | **0.11** | ~1× | catastrophic |

H and H5 produce catastrophic FPR damage at a twin fraction of **~0.0005 — roughly
200× below the paper's copy-fidelity 0.11** — but at a ratio-to-floor of ~1. The
twin fraction measures the near-exact-duplicate *tail*; the damage sets in once the
mimic reaches the benign *cluster* (ratio ≈ 1), which happens well before the tail
fills. The absolute twin fraction therefore **understates** the danger of real
traffic, while the ratio to the benign floor tracks it: 46× (L) → no damage, ~1×
(H, H5) → catastrophic. The paper should report and reason about the ratio to the
floor, citing these numbers (twin 0.0005 yet 0.95× floor and ΔFPR +0.62) as the
reason the absolute twin fraction is the wrong lens.
