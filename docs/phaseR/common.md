# Phase R — rules every cloud session follows

Read this before doing anything else. Your own session file
(`docs/phaseR/session-<item>.md`) tells you which item to run; this file tells you how.

**Check progress every 30 minutes, not more often. Keep messages short.**

## 1. Follow DECISIONS §31 exactly

`docs/DECISIONS.md` §31 is the pre-registration for all of Phase R: hypothesis, cells, seeds,
test, correction, and the exact bar for "holds" / "does not hold" / "mixed" (and, where a bar
says so, "not evaluable"). It was written and committed **before** any Phase R run. Run exactly
what it specifies. **Do not change DECISIONS.md.** If you think a cell is wrong, mis-specified,
or missing, say so in your results write-up (`docs/phaseR/<item>-results.md`) rather than
editing the pre-registration to match what you ran. A pre-registration that gets edited after
the fact to fit the result is worthless, and the results write-up is exactly where that
disagreement belongs.

Whatever a cell's outcome is, report it as measured. A clean "does not hold" is as useful as a
"holds"; do not re-run a cell with different settings to see whether it holds on a second try.

The paired $t$-test is the primary test (§31, "Common statistical machinery"); the permutation
test is reported alongside. Use `experiments/phase0_stats_recompute.py`'s paired-$t$ /
permutation machinery (import it, don't reimplement it), the same way the Phase A sessions did
(`experiments/phaseA_*_stats.py` are worked examples).

## 2. Get the data

You cannot see the laptop this was prepared on. Clone the private data repo and unzip into
`data/`, exactly:

```
git clone --depth 1 https://github.com/harshitchhabi/IDS-data /tmp/IDS-data
mkdir -p data/cicids2017 data/cicids2017-fixed data/unsw-nb15 data/netflow-v2

python -c "
import zipfile, glob, os, shutil
for src_dir, dst_dir in [
    ('/tmp/IDS-data/cicids2017', 'data/cicids2017'),
    ('/tmp/IDS-data/cicids2017-fixed', 'data/cicids2017-fixed'),
    ('/tmp/IDS-data/unsw-nb15', 'data/unsw-nb15'),
    ('/tmp/IDS-data/netflow-v2', 'data/netflow-v2'),
]:
    for z in glob.glob(os.path.join(src_dir, '*.zip')):
        with zipfile.ZipFile(z) as f:
            f.extractall(dst_dir)
        print('extracted', z, '->', dst_dir)
    for c in glob.glob(os.path.join(src_dir, '*.csv')) + glob.glob(os.path.join(src_dir, '*.json')):
        shutil.copy(c, dst_dir)
"
```

`unsw-nb15/NUSW-NB15_features.csv` is a plain CSV, not zipped: the copy step above is what puts
it in `data/unsw-nb15/`. Without it the UNSW-NB15 loader refuses to run, by design. **Check
`IDS-data`'s own README first:** `netflow-v2/` (R3's data) may not exist yet; it depends on a
manual download (§31.4). If a directory your item needs is empty or missing after extraction,
stop and say so in your results write-up. Do not substitute a different dataset, and do not
skip the cell silently.

`gh repo clone harshitchhabi/IDS-data /tmp/IDS-data -- --depth 1` works if plain `git clone` is
blocked by the GitHub App's token scope.

**Attaching `IDS-data` needs an approval (`add_repo`).** The GitHub App has access, but the
session's sandbox only sees the repo once an `add_repo` / attach-repo request for
`harshitchhabi/IDS-data` is approved, the first time you touch it. Expect one interactive
approval before the clone succeeds; if the clone hangs or 404s, that approval is what's
missing, not the repo.

**Build the loop dataset cache before running anything else.** `experiments/phase0_loop.py` loads
`data/loop/<dataset>.npz`, a gitignored derived cache the extraction above does not create.
Build it once per dataset your item uses, right after extraction, **with this commit's code**.
`--eval-redraw` (R1.a) needs the full trusted_eval arrays, and R2.4's stale-replay filler needs
`seed_family` (§31.6). Only a cache built by current code contains both, and the runner refuses
an older cache rather than guessing:

```
python -m experiments.phase0_loop_data --source cicids          # R1, R2
python -m experiments.phase0_loop_data --source cicids-fixed    # R2 only
python -m experiments.phase0_loop_data --source unsw-nb15       # R2 only
# R3 builds its own NetFlow v2 caches in its prep stage (session-r3.md)
```

This is unmodified from Phase A apart from the extra arrays: the existing arrays are
byte-identical to an older build of the same data (verified before §31 was committed).
Without this step the first run fails with `FileNotFoundError` on the `.npz`, which is not a data
problem.

## 3. VM resources

Expect 4 vCPU / 16 GB, but **the VM has been seen with as little as 1 vCPU**, so check `nproc`
before assuming either. The run scripts default to `WORKERS=3`. Do not raise it regardless of
core count: 4 workers have OOM'd on comparably sized jobs in this project. R2's ratio-0.9 arms
train on ~10x the seed set and the MLP is the slowest model here; on 1 vCPU, expect R2 on
CICIDS2017 to take many hours, and budget for it rather than treating a quiet log as stalled.
The scripts already export `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`.

## 4. Long sweeps run in the background

Every item's commands are one script, `experiments/run_phaseR_<item>.sh` (the session file
gives the exact invocation). Run it under `nohup` with a log:

```
mkdir -p results/phaseR/<item>
nohup bash experiments/run_phaseR_<item>.sh <args> > results/phaseR/<item>/run_<args>.log 2>&1 &
```

**Check progress every 30 minutes**, by counting files under `results/phaseR/<item>/.../jobs/`
or `tail`ing the log. `phase0_loop.py` prints a `{"done": N, "of": M}` line every 10 finished
jobs, not on a timer, so a quiet log is normal. Keep each check-in message short: one line with
jobs done / total and any error.

Sweeps resume from existing result files (one CSV per job under `<out>/jobs/`; a file that
exists is skipped). **If the VM restarts, your shell dies, or a command needs re-issuing for any
reason, re-run the exact same command.** Do not delete partial output and start over, and do not
try to hand-resume from a specific seed.

## 5. Stay on your branch; stay in your lane

**Cloud sessions push to their own `claude/<session-name>` branch, not to a `phase-r-<item>`
branch.** Each cloud session creates its own working branch automatically. Your commits land
there, and that is fine: it is what happened for every Phase A item. The merge step reads from
whatever branch you pushed to. Don't force a push to any other branch. Note your actual branch
name at the top of your results write-up so it's easy to find.

Commit and push **every hour, or after each script invocation finishes**, whichever comes first.
If your session is interrupted, partial progress on `origin` is what lets it be picked back up.

Write results to `results/phaseR/<item>/` (the run scripts' default output root) and the
write-up to `docs/phaseR/<item>-results.md`. Your statistics script goes in
`experiments/phaseR_<item>_stats.py`.

**Do not edit:** `docs/DECISIONS.md`, `experiments/run_phaseR_*.sh` (the pre-registered
commands), anything under `paper/`, `results/phase0/`, `results/phaseA/`, `src/dloop/demo/`,
`src/dloop/api/`, or `scripts/`. Three sessions run in parallel; touching any of these is how they
collide on merge. If your item genuinely needs a code change, keep it under `src/dloop/` or
`experiments/` and scoped to what your item needs. If a pre-registered command itself fails,
stop and report it rather than editing the script.

## 6. Finish

End `docs/phaseR/<item>-results.md` with one table, one row per pre-registered cell:

| cell | n | effect | 95% CI | $t$ | $p_t$ | $p_{\rm perm}$ | Holm | vs. §31 bar |
|---|---|---|---|---|---|---|---|---|

...followed by one paragraph per bar stating **holds / does not hold / mixed** (or **not
evaluable**, where the bar defines it) against the exact §31 bar. Quote the bar, don't
paraphrase it, and don't substitute your own judgment about whether the result "looks similar
enough." For a mixed result, name the condition that passed and the one that failed, the same
way DECISIONS.md's own entries do.

Push. Stop. Do not start on a different item, and do not go back and adjust an earlier run
because a later one made you reconsider it. If that happens, write it up as a limitation in your
results file instead.
