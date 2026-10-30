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
