# Phase A — rules every cloud session follows

Read this before doing anything else. Your own session file
(`docs/phaseA/session-<item>.md`) tells you which item to run; this file tells you how.

## 1. Follow DECISIONS §29 exactly

`docs/DECISIONS.md` §29 is the pre-registration for all of Phase A — hypothesis, cells, seeds,
test, correction, and the exact bar for "replicates" / "does not replicate" / "mixed", for all
three items. It was written and committed **before** any Phase A run. Run exactly what it
specifies. **Do not change DECISIONS.md.** If you think a cell is wrong, mis-specified, or
missing, say so in your results write-up (`docs/phaseA/<item>-results.md`) rather than editing
the pre-registration to match what you ran — a pre-registration that gets edited after the fact
to fit the result is worthless, and the result section is exactly the place that disagreement
belongs.

Whatever a cell's outcome is — replicates, does not replicate, mixed — report it as measured.
A clean non-replication is the most useful thing this round can produce; do not re-run a cell
with different settings to see if it replicates on a second try.

## 2. Get the data

You cannot see the laptop this was prepared on. Clone the private data repo (the GitHub App
this session runs under has access to it) and unzip into `data/`, exactly:

```
git clone --depth 1 https://github.com/harshitchhabi/IDS-data /tmp/IDS-data
mkdir -p data/cicids2017 data/cicids2017-fixed data/unsw-nb15

python -c "
import zipfile, glob, os
for src_dir, dst_dir in [
    ('/tmp/IDS-data/cicids2017', 'data/cicids2017'),
    ('/tmp/IDS-data/cicids2017-fixed', 'data/cicids2017-fixed'),
    ('/tmp/IDS-data/unsw-nb15', 'data/unsw-nb15'),
]:
    for z in glob.glob(os.path.join(src_dir, '*.zip')):
        with zipfile.ZipFile(z) as f:
            f.extractall(dst_dir)
        print('extracted', z, '->', dst_dir)
"
```

`data/cicids2017/` is what `src/dloop/sim/cicids.py`'s `DEFAULT_ROOT` already expects —
`--dataset cicids` needs no further setup once this runs. `data/cicids2017-fixed/` and
`data/unsw-nb15/` are new; whichever of these your item needs, check
**`https://github.com/harshitchhabi/IDS-data` 's own README first** — not every dataset may be
present (UNSW-NB15 in particular needs a manual download that may or may not have happened by
the time you run; the README says so explicitly if it hasn't). If a directory you need is empty
or missing after the extraction above, stop and say so in your results write-up rather than
substituting a different dataset or skipping the cell silently.

`gh repo clone` also works if plain `git clone` is ever blocked by the GitHub App's token scope;
try that as a fallback, same `--depth 1`.

## 3. VM resources

4 vCPU / 16 GB. Every `experiments/phase0_loop.py` invocation in your session file already has
`--workers 3` baked in — do not raise it (`--workers 4` has OOM'd on comparably-sized jobs on
smaller machines in this project before; 3 is the known-safe number here). Set these once per
shell before any run:

```
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
```

`Model.fit` (`src/dloop/models/base.py`) casts every model's input to float64 before scaling —
that's existing, unconditional behavior, not something to change. The two PyTorch models (MLP,
autoencoder) then cast to `torch.float32` internally before training, which is also already the
case; nothing to configure for memory on this VM.

## 4. Long sweeps run in the background

```
nohup python -m experiments.phase0_loop <args> > results/phaseA/<item>/run.log 2>&1 &
```

Check progress roughly every 15 minutes (`tail -f run.log`, or count files under
`results/phaseA/<item>/jobs/`) — not more often; checking every minute burns your own session
budget for no benefit, since `phase0_loop.py` writes a `{"done": N, "of": M}` progress line only
every time a job finishes, not on a timer.

Sweeps resume from existing result files (`<out>/jobs/*.csv`, one file per
(scenario, model, seed, jitter, ratio) job — a file that already exists is skipped, not
recomputed). **This means: if the VM restarts, your shell dies, or a command needs to be
re-issued for any reason, re-run the exact same command.** Do not delete partial output and
start over, and do not try to hand-resume from a specific seed — the file-existence check already
does that correctly.

## 5. Stay on your branch; stay in your lane

Work only on the branch named in your session file. Commit and push **every hour, or after each
sub-step finishes** (a sub-step = one of the `python -m experiments.phase0_loop` invocations in
your session file completing) — whichever comes first. Don't batch everything into one commit at
the end; if your session is interrupted, partial progress on `origin` is what lets it (or you)
pick back up.

Write results to `results/phaseA/<item>/` (job CSVs land under `results/phaseA/<item>/jobs/`
automatically from the `--out` flag already in your session file's commands) and the write-up to
`docs/phaseA/<item>-results.md`.

**Do not edit:** `docs/DECISIONS.md`, anything under `paper/`, anything under `src/dloop/demo/`
or `src/dloop/api/` (the dashboard/demo), or anything under `scripts/`. Three sessions are running
in parallel on three branches; touching any of these is how they'd collide on merge. If your item
genuinely needs a code change outside `src/dloop/loop/`, `src/dloop/models/`, `src/dloop/sim/`,
`src/dloop/features/`, or `experiments/` (item B's dataset loaders are the expected case — new
files under `src/dloop/sim/` and `src/dloop/features/`, following `cicids.py`'s existing pattern),
make it, but keep the diff scoped to what your item needs.

## 6. Finish

End `docs/phaseA/<item>-results.md` with one table, one row per pre-registered cell:

| cell | n | effect | 95% CI | $t$ | $p_t$ | $p_{\rm perm}$ | vs. §29 bar |
|---|---|---|---|---|---|---|---|

...followed by one paragraph per family stating **replicated / did not replicate / mixed** against
the exact §29 bar for that family (quote the bar, don't paraphrase it) — not your own judgment
call about whether the result "looks similar enough." Mixed results get the specific condition
that passed and the one that failed named explicitly, the same way DECISIONS.md's own entries do
when a pre-registered bar is only partly met.

Push. Stop. Do not start on a different item, and do not go back and adjust an earlier run because
a later one made you reconsider it — if that happens, write it up as a limitation in your results
file instead.
