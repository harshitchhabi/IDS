# Demo walkthrough (5 minutes)

**Start:** `python scripts/run.py demo`. It opens `http://127.0.0.1:8000` in a browser. Everything binds to
127.0.0.1 only. If anything about the live path is broken on the day, click **switch to recorded** at the top
right — it replays the exact rounds from the same code, no retraining required (see "If something breaks"
below).

Two things are always true and worth saying once up front: the loop control panel (S0 / A1 / defenses) runs
the *real* research code — `dloop.loop.live.LiveLoop` calls the same adversaries, labeler, defenses and models
as the archived experiments, and a test (`tests/test_live.py`) asserts it reproduces them row for row. The
traffic stream is real CICIDS2017 flows from `trusted_eval`, scored but never trained on.

## 1. Clean loop (S0) — ~40s

Click **① Clean honeypot feed (S0)**. Say: *"The honeypot is sending genuine attack traffic. Auto-labeled
malicious, retrained every few seconds."* Watch the **True-positive rate per round** chart climb and the
**False-positive rate per round** chart stay flat near 1%. This is the checkpoint the whole project depends
on: if the honest loop didn't improve the detector, nothing past this point would mean anything.

Let 5-6 rounds run (S0 dots are green on the round charts).

## 2. Poison the loop (A1) — the FPR-blowup moment — ~60s

Click **② Poison attack (A1)**. Say: *"Same auto-labeling policy — everything the honeypot sees is stamped
malicious. Now the adversary points the benign traffic generator at the honeypot instead."*

Watch two things at once:
- **False-positive rate per round** climbs past 50-70% within about 10 rounds.
- **True-positive rate per round** *also climbs*, past 90%. Say this line explicitly: **"TPR going up here does
  not mean the detector is getting better — it's flagging everything, benign included."** Point at the
  **Precision per round** chart next to it: precision collapses from ~100% to under 30% over the same rounds.
  That's the tell an audience (or a dashboard without this chart) would miss.

Let A1 run until FPR is clearly elevated (10-12 rounds is usually enough) before moving to defenses.

## 3. Defenses, in turn — the punchline — ~90s

With A1 still feeding, click through the three defense buttons, giving each 1-2 rounds:

1. **③ ShareCap (c=0.05)** — FPR drops back to ~1-2% almost immediately.
2. **D1 (cost weighting)** — also recovers, to about the same FPR/TPR.
3. **kNN sanitize** — also recovers, to about the same FPR/TPR.

Then point at the **Defense comparison** table's rightmost column, **defense cost / round**. Say the line the
whole research turns on: **"ShareCap needs no cost model, no reference data beyond a share cap, and doesn't
even know the poison ratio — and it matches the complex defenses at roughly 1/80th the per-round cost of
kNN."** (The exact multiple is on screen — it's the `kNN ms / ShareCap ms` note under the table.) That a
trivial cap matches sophisticated defenses is the paper's finding, not a demo simplification: see
`docs/DECISIONS.md` §24-25.

## 4. Reset and the honeypot panel — ~30s

Click **Reset** to return to round 0. Scroll to **Honeypot activity**. Say: *"This is a real Cowrie SSH
honeypot, not a simulation — separate from the loop above."* If a live attack hasn't been run yet, run:

```
python scripts/attack_honeypot.py
```

and the sessions, credentials tried and commands run will appear within a few seconds, each with a live
**effort score**. Say: *"This is the session-level signal the loop's flow data can't give D1 — auth attempts,
commands, bytes, duration. DECISIONS §25.4 found flow-level cost proxies are insufficient on CICIDS; this
panel is the research reason the live Cowrie testbed exists."* Point out explicitly that Cowrie sessions are
**not** CICFlowMeter flows and do **not** feed the model — the label under the panel title says so.

## Optional: attack burst

Anywhere after step 1, click **Launch attack (500 flows)** with a family selected (DDoS is the most visible).
The traffic chart spikes and matching alerts appear in the alert stream within about a second.

## If something breaks

Click **switch to recorded** (top right badge area). The dashboard keeps working off `results/demo/recorded.json`
— the same S0 → A1 → defense story, captured from a real run ahead of time — with no training or CICIDS data
required. The badge turns amber and says **RECORDED**. If the live path breaks *before* the demo starts, launch
straight into recorded mode: `python scripts/run.py demo --recorded`.

If both fail, the backup screen recording is at `docs/demo/walkthrough.mp4` (or `.gif`) and the screenshots
`docs/demo/day1_burst.png`, `day2_a1_poisoned.png`, `day2_sharecap.png`, `precision_check.png` and
`day3_cowrie.png` tell the same story as still images.

## What NOT to click

- Don't leave A1 running past ~15 rounds before switching defenses — the fixed threshold FPR can approach 100%,
  and it takes longer to visibly recover.
- The model is Random Forest, not XGBoost. `docs/DECISIONS.md` §25.x found XGBoost's FPR response to A1 is
  seed-dependent (bimodal across only 5 archived seeds) while RF climbs reliably on all of them — this was a
  deliberate choice for a live demo, not an oversight, and is worth saying if asked.
