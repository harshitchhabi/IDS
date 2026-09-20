"""Four-way partition of the Phase 0 dataset, with temporal-leakage guards.

CLAUDE.md, Phase 0: four **disjoint** sets — ``seed_train``, ``prod_benign``,
``honeypot_pool``, ``trusted_eval`` — split to avoid temporal leakage.

Two strategies (``PartitionConfig.strategy``):

``within_day_temporal`` *(default)*
    Split each **(day, family) block** along its own timeline. CICIDS2017 runs
    its attacks in sequential time blocks within a day (Friday = Bot morning,
    PortScan midday, DDoS afternoon), so a per-day temporal cut would route
    whole families into single partitions and re-create the day-split problem
    at finer granularity. Grouping by (day, family), sorting each group by
    timestamp and cutting by cumulative fraction puts every family in every
    partition with temporal ordering intact:

      * benign  -> ``seed_train`` | ``prod_benign`` | ``honeypot_pool`` | ``trusted_eval``
      * attack  -> ``seed_train`` | ``honeypot_pool`` | ``trusted_eval``

    The eval-family arms are then set explicitly, not left to chance:
    ``pool_withheld_families`` (A4) keeps a family out of ``honeypot_pool`` so it
    lands in ``seed_only``; ``seed_withheld_families`` keeps one out of
    ``seed_train`` so it lands in ``honeypot_only`` (the loop teaching a
    decoy-only family); a family in both lists is ``novel``.

``day_split``
    Whole days routed to whole partitions (:data:`DAY_TO_PARTITION`). Retained
    as a robustness check only.

Leakage guards (``within_day_temporal``), all reported, none silently passed —
because CICIDS2017 attacks are automated-tool bursts whose early and late flows
are near-identical, so a naive temporal cut can leave ``honeypot_pool`` and
``trusted_eval`` near-identical and let S0 "improve" by memorizing a fingerprint
and *false-pass* the checkpoint:

  a. Hard de-duplication before splitting — exact duplicates (in
     :mod:`dloop.features.cleaning`) plus near-duplicates here: two half-offset
     grid snaps in normalized feature space, run globally so cross-day pairs are
     caught. The grid resolution is a swept, evidence-justified parameter
     (DECISIONS.md §11) because on real data it removes a large fraction of the
     benign class.
  b. Burst-level assignment, not a row-level time cut (DECISIONS.md §14). A
     temporal cut through a flood tool's output separates nothing — consecutive
     rows in one burst are near-identical and the tool's behaviour does not
     change over its run, so whichever side of the cut they land on, the other
     side still "sees" the same fingerprint. Each (day, family) stream is first
     segmented into contiguous episodes using inter-flow time gaps
     (``burst_gap_seconds``), then whole bursts — never a fraction of one — are
     assigned to partitions, filling toward the configured split fractions by
     cumulative row count. A guard band (``boundary_buffer_seconds``) around
     each realized partition boundary is kept as a secondary check: it only
     drops rows when two adjacent bursts happen to sit closer in time than the
     band, which the burst cut alone does not guarantee.
  c. Nearest-neighbour distance, in normalized feature space, from each
     ``trusted_eval`` row to its closest ``honeypot_pool`` row of the same
     class. Reported for both classes; only the **attack** class gates
     ``leak_warning`` (near-identical benign flows across partitions are the
     normal state of real traffic, not a leak). Concentration near zero on the
     attack class means the partition is leaking and any S0 gain is
     memorization — callers must stop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.features.cleaning import CleaningReport, clean_flows
from dloop.features.normalize import Normalizer, fit_normalizer
from dloop.logging_config import get_logger

log = get_logger("sim.partition")

PARTITIONS: tuple[str, ...] = ("seed_train", "prod_benign", "honeypot_pool", "trusted_eval")

# within_day_temporal: which partition each time-ordered segment of a stream
# goes to. The adversary pool (honeypot_pool) is deliberately TWO-CLASS: it
# needs benign rows for A1's mimicry and attack rows for S0 and A4, all drawn
# from the same middle-of-day temporal slice, disjoint from seed_train and
# trusted_eval. An attack-only pool cannot express A1, the paper's central attack.
BENIGN_ROUTE: tuple[str, ...] = ("seed_train", "prod_benign", "honeypot_pool", "trusted_eval")
ATTACK_ROUTE: tuple[str, ...] = ("seed_train", "honeypot_pool", "trusted_eval")

# Canonical A1 poison-ratio sweep. Log-spaced, not linear: if A1 does real
# damage it shows at the low end, which is where resolution matters.
POISON_SWEEP: tuple[float, ...] = (0.0, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5)

# day_split: whole capture day -> whole partition.
DAY_TO_PARTITION: dict[str, str] = {
    "monday": "seed_train",
    "tuesday": "seed_train",
    "wednesday": "prod_benign",
    "thursday": "honeypot_pool",
    "friday": "trusted_eval",
}
BENIGN_ONLY: frozenset[str] = frozenset({"prod_benign"})


@dataclass
class PartitionConfig:
    strategy: Literal["within_day_temporal", "day_split"] = "within_day_temporal"

    # within_day_temporal — time fractions per stream (each must sum to 1).
    # benign feeds 4 partitions (incl. the adversary pool), attack feeds 3.
    benign_split: tuple[float, float, float, float] = (0.30, 0.20, 0.30, 0.20)
    attack_split: tuple[float, float, float] = (0.40, 0.40, 0.20)

    # Guard (b): burst segmentation + whole-burst assignment, not a row-level
    # time cut. Two consecutive rows in the same (day, family) stream separated
    # by more than this many seconds start a new burst; bursts are never split
    # across partitions. Chosen from the reported per-family inter-arrival
    # distribution (DECISIONS.md §14): most families have a clear gap structure
    # at 1-2s (session/tool-retry boundaries); a couple of flood families
    # (DDoS, DoS Hulk) are near-continuous but still yield hundreds of bursts at
    # this threshold, which is enough resolution to fill the split fractions.
    # NOTE: the MachineLearningCVE CICIDS2017 CSVs have no timestamp; the cleaner
    # synthesizes 1 row = 1 s in file order, so on that data these "seconds" are
    # file-order row counts (DECISIONS.md §14 erratum).
    burst_gap_seconds: float = 2.0

    # Secondary check on the burst assignment: if two adjacent bursts assigned
    # to different partitions land closer than this in time, drop rows within
    # half this band of the boundary. Bursts already guarantee a gap >=
    # burst_gap_seconds, so this rarely fires; it exists as defense in depth,
    # not as the primary leakage guard (that is burst assignment itself).
    boundary_buffer_seconds: float = 300.0
    max_buffer_frac: float = 0.25  # shrink the band rather than exceed this per stream

    # Guard (a): near-duplicate grid cell size in normalized (log-IQR) units.
    # 0 disables. ~0.02 == 2% of an IQR; larger removes more aggressively.
    near_dup_grid: float = 0.02

    # Guard (c): flag leakage if the 5th-percentile normalized NN distance
    # (per-feature RMS) from trusted_eval attacks to honeypot_pool attacks is
    # below this.
    nn_leak_p5_threshold: float = 0.25

    # Family withholding — the two knobs that carve the eval-family arms out of
    # the default "everything seen_both" baseline:
    #   pool_withheld_families  removed from honeypot_pool  -> seed_only (this is A4)
    #   seed_withheld_families   removed from seed_train      -> honeypot_only
    #   a family in both lists is in trusted_eval only        -> novel
    pool_withheld_families: tuple[str, ...] = ()
    seed_withheld_families: tuple[str, ...] = ()

    # Guard (c): cap the query side of the NN search (the honeypot_pool index
    # stays complete, so a real near-duplicate is still found). Keeps the check
    # tractable on CICIDS2017's millions of rows; 0 disables the cap.
    nn_check_query_sample: int = 40_000

    seed: int = 20250903

    def __post_init__(self) -> None:
        for name, s, k, route in (
            ("benign_split", self.benign_split, 4, BENIGN_ROUTE),
            ("attack_split", self.attack_split, 3, ATTACK_ROUTE),
        ):
            if len(s) != k or abs(sum(s) - 1.0) > 1e-9 or any(x < 0 for x in s):
                raise ValueError(f"{name} must be {k} non-negative fractions summing to 1: {s}")
            assert len(route) == k


@dataclass
class LeakageReport:
    strategy: str
    near_dups_removed: dict[str, dict[str, int]] = field(default_factory=dict)   # day -> class -> n
    buffer_rows_removed: dict[str, int] = field(default_factory=dict)            # "day/family" -> n
    # guard (b): burst segmentation stats per (day, family) stream.
    bursts_per_stream: dict[str, dict] = field(default_factory=dict)
    # guard (c): NN distance trusted_eval -> nearest honeypot_pool row, run per
    # class. {"attack"|"benign": {"percentiles": {...}, "frac_below_grid": float}}
    nn_distance: dict[str, dict] = field(default_factory=dict)
    nn_by_family: dict[str, dict] = field(default_factory=dict)  # te attack family -> stats
    leak_warning: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class PartitionedData:
    frames: dict[str, pd.DataFrame]
    cleaning: dict[str, CleaningReport]
    leakage: LeakageReport
    config: PartitionConfig
    normalizer: Normalizer

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.frames[name]

    def families_by_partition(self) -> dict[str, set[str]]:
        return {
            p: set(df.loc[df[schema.BINARY_LABEL] == 1, schema.LABEL].unique())
            for p, df in self.frames.items()
        }

    # A trusted_eval attack family with fewer than this many rows cannot support
    # a stable per-family TPR and is excluded from per-family reporting (its rows
    # stay in the data).
    MIN_FAMILY_ROWS = 500

    def eval_family_arm(self, family: str) -> str:
        """Which coverage arm a family falls in, by where it actually appears."""
        fam = self.families_by_partition()
        in_seed = family in fam["seed_train"]
        in_pool = family in fam["honeypot_pool"]
        if in_seed and in_pool:
            return "seen_both"
        if in_seed:
            return "seed_only"       # A4's controlled arm
        if in_pool:
            return "honeypot_only"   # the loop teaching a decoy-only family
        return "novel"

    def eval_family_split(self) -> dict[str, list[str]]:
        """trusted_eval attack families grouped into the four coverage arms.

        * ``seen_both``     — in seed_train AND honeypot_pool.
        * ``seed_only``     — in seed_train, withheld from honeypot_pool (A4).
        * ``honeypot_only`` — in honeypot_pool, not in seed_train (the detector
          learning a family it only saw through the decoy — S0's most
          interesting arm).
        * ``novel``         — in neither.

        None of these is ever folded into an aggregate.
        """
        te = self.families_by_partition()["trusted_eval"]
        arms: dict[str, list[str]] = {
            "seen_both": [], "seed_only": [], "honeypot_only": [], "novel": []
        }
        for f in sorted(te):
            arms[self.eval_family_arm(f)].append(f)
        return arms

    def _arm_source(self, family: str, arm: str) -> str:
        """Whether a non-``seen_both`` arm was set on purpose or fell out of the
        split. ``config`` = the family is in a withholding list; ``artifact`` =
        it landed there because its (day, family) block was too small or too
        time-skewed to yield all segments (watch for these — they are not
        controlled manipulations)."""
        if arm == "seen_both":
            return "-"
        cfg = self.config
        if cfg.strategy != "within_day_temporal":
            return "strategy"   # day_split routes whole days -> every eval family is novel
        if arm == "seed_only":
            return "config" if family in cfg.pool_withheld_families else "artifact"
        if arm == "honeypot_only":
            return "config" if family in cfg.seed_withheld_families else "artifact"
        return "config" if (family in cfg.pool_withheld_families
                            and family in cfg.seed_withheld_families) else "artifact"

    def eval_family_stats(self) -> pd.DataFrame:
        """Per-family row counts across the partitions + arm + reportable flag."""
        te = self.frames["trusted_eval"]
        seed = self.frames["seed_train"]
        pool = self.frames["honeypot_pool"]
        te_atk = te[te[schema.BINARY_LABEL] == 1]
        rows = []
        for fam, n_eval in te_atk[schema.LABEL].value_counts().items():
            arm = self.eval_family_arm(str(fam))
            rows.append({
                "family": str(fam),
                "arm": arm,
                "arm_source": self._arm_source(str(fam), arm),
                "n_seed_train": int((seed[schema.LABEL] == fam).sum()),
                "n_honeypot_pool": int((pool[schema.LABEL] == fam).sum()),
                "n_trusted_eval": int(n_eval),
                "reportable": bool(n_eval >= self.MIN_FAMILY_ROWS),
            })
        return pd.DataFrame(rows).sort_values(["arm", "family"]).reset_index(drop=True)

    def summary(self) -> pd.DataFrame:
        rows = []
        for name in PARTITIONS:
            df = self.frames[name]
            n = len(df)
            n_attack = int(df[schema.BINARY_LABEL].sum())
            rows.append(
                {
                    "partition": name,
                    "rows": n,
                    "benign": n - n_attack,
                    "attack": n_attack,
                    "attack_frac": round(n_attack / n, 4) if n else 0.0,
                    "days": ",".join(sorted(df[schema.DAY].unique())),
                    "classes": ",".join(sorted(df[schema.LABEL].unique())),
                }
            )
        return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# row hashing                                                                 #
# --------------------------------------------------------------------------- #
def _row_hashes(df: pd.DataFrame) -> np.ndarray:
    """Per-row uint64 content hash over features + label (ignores day / timestamp).
    Rolling hash over one column at a time — never materializes a second copy of
    a millions-row feature block."""
    lab = pd.util.hash_array(df[schema.LABEL].to_numpy())   # deterministic across calls
    h = lab * np.uint64(1000003) + np.uint64(11)
    for feat in schema.CANONICAL_FEATURES:
        # 6 decimal places — matches "the same flow" without float64 fragility
        q = np.rint(df[feat].to_numpy("float64") * 1e6).astype(np.int64) + (1 << 44)
        h = h * np.uint64(1000003) + q.astype(np.uint64)
    return h


# --------------------------------------------------------------------------- #
# guard (a): near-duplicate removal                                           #
# --------------------------------------------------------------------------- #
def _remove_near_duplicates(
    df: pd.DataFrame, normalizer: Normalizer, grid: float, report: LeakageReport
) -> pd.DataFrame:
    """Drop near-duplicate rows (within ~``grid`` per-feature-RMS of a kept row
    of the same label) before the temporal split.

    Two O(n) grid snaps. The first rounds normalized features to a ``grid``
    lattice and keeps one row per (cell, label); the second repeats on a
    half-cell-shifted lattice. A near-duplicate pair that straddled a cell
    boundary in the first snap — the leak a single grid pass misses — lands in
    the same shifted cell and is caught by the second. Both passes are linear,
    which matters: on real CICIDS2017 a single DoS burst is hundreds of
    thousands of near-identical rows and a radius graph over them does not fit
    in memory. Runs on the whole dataset at once so a cross-day near-duplicate
    pair is caught too."""
    if grid <= 0 or len(df) < 2:
        return df

    x = normalizer.transform(df)                       # float32, clipped to +-25
    lab_codes = pd.factorize(df[schema.LABEL].to_numpy())[0].astype(np.int64)
    labels = df[schema.LABEL].to_numpy()
    days = df[schema.DAY].to_numpy()
    drop = np.zeros(len(df), dtype=bool)

    for offset in (0.0, 0.5):
        live = np.where(~drop)[0]
        # rolling hash of (grid cell per feature, label) -> one uint64 per row.
        # keys are small ints (|x|<=25) so a 64-bit polynomial hash is collision-safe
        # enough for a dedup sanity pass.
        h = lab_codes[live].astype(np.uint64)
        for j in range(x.shape[1]):
            cell = np.rint(x[live, j] / grid + offset).astype(np.int64) + (1 << 20)
            h = h * np.uint64(1000003) + cell.astype(np.uint64)
        dup = pd.Series(h).duplicated(keep="first").to_numpy()
        drop[live[dup]] = True

    if drop.any():
        removed = pd.DataFrame({"day": days[drop], "label": labels[drop]})
        for day, g in removed.groupby("day", sort=True):
            report.near_dups_removed[str(day)] = {
                str(k): int(v) for k, v in g["label"].value_counts().items()
            }
        log.info("near-duplicate rows removed (global)", total=int(drop.sum()),
                 by_day={d: sum(v.values()) for d, v in report.near_dups_removed.items()},
                 grid=grid)
    return df.loc[~drop].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# within_day_temporal split                                                   #
# --------------------------------------------------------------------------- #
def _burst_ids(ts: np.ndarray, gap_seconds: float) -> np.ndarray:
    """Per-row burst id (0-based, ascending) for a time-sorted timestamp array.
    A new burst starts whenever the gap to the previous row exceeds
    ``gap_seconds``."""
    if len(ts) <= 1:
        return np.zeros(len(ts), dtype=np.int64)
    gaps_s = np.diff(ts) / np.timedelta64(1, "s")
    new_burst = np.concatenate(([True], gaps_s > gap_seconds))
    return np.cumsum(new_burst) - 1


def _split_stream_temporal(
    stream: pd.DataFrame,
    split: tuple[float, ...],
    route: tuple[str | None, ...],
    cfg: PartitionConfig,
    tag: str,
    report: LeakageReport,
) -> list[tuple[str, pd.DataFrame]]:
    """Split one time-sorted (day, family) group into ``len(route)`` segments at
    burst granularity: segment the stream into contiguous bursts (guard b),
    then assign whole bursts to segments in temporal order, filling toward the
    cumulative ``split`` fractions by row count. No burst is ever divided
    across a partition boundary. ``route`` entries of ``None`` drop that
    segment (a fully-withheld family arm); repeated partition names
    accumulate. A guard band around each realized boundary is applied as a
    secondary check (see module docstring, guard b)."""
    out: list[tuple[str, pd.DataFrame]] = []
    if stream.empty:
        return out
    s = stream.sort_values(schema.TIMESTAMP, kind="stable")
    ts = s[schema.TIMESTAMP].to_numpy("datetime64[ns]")
    n = len(ts)

    burst_id = _burst_ids(ts, cfg.burst_gap_seconds)
    n_bursts = int(burst_id[-1]) + 1
    burst_sizes = np.bincount(burst_id, minlength=n_bursts)
    report.bursts_per_stream[tag] = {
        "n_rows": int(n), "n_bursts": int(n_bursts),
        "median_burst_size": float(np.median(burst_sizes)),
        "max_burst_size": int(burst_sizes.max()),
    }

    # walk bursts in temporal order, advancing the target segment once the
    # running row count (before this burst) has reached its cumulative target
    targets = np.cumsum(split)[:-1] * n   # boundary row-count targets, len(route)-1
    seg_of_burst = np.empty(n_bursts, dtype=np.int64)
    seg_idx, running = 0, 0
    for b in range(n_bursts):
        while seg_idx < len(split) - 1 and running >= targets[seg_idx]:
            seg_idx += 1
        seg_of_burst[b] = seg_idx
        running += burst_sizes[b]
    row_seg = seg_of_burst[burst_id]

    # guard (b), secondary check: measure the realized time gap at each
    # internal boundary between adjacent segments actually present in route;
    # if it is thinner than boundary_buffer_seconds, drop a band around it.
    band_ns = int(cfg.boundary_buffer_seconds * 1e9 / 2)
    in_band = np.zeros(n, dtype=bool)
    while band_ns > 0:
        in_band = np.zeros(n, dtype=bool)
        for i in range(len(route) - 1):
            rows_i = np.where(row_seg == i)[0]
            rows_j = np.where(row_seg == i + 1)[0]
            if len(rows_i) == 0 or len(rows_j) == 0:
                continue
            hi, lo = ts[rows_i].max(), ts[rows_j].min()
            if (lo - hi) / np.timedelta64(1, "ns") < band_ns * 2:
                mid = hi + (lo - hi) // 2
                band_td = np.timedelta64(band_ns, "ns")
                in_band |= (ts >= mid - band_td) & (ts < mid + band_td)
        if in_band.mean() <= cfg.max_buffer_frac:
            break
        band_ns //= 2
    if in_band.any():
        key = f"{tag}"
        report.buffer_rows_removed[key] = report.buffer_rows_removed.get(key, 0) + int(in_band.sum())
        log.info("boundary guard band dropped rows (secondary check)", stream=tag,
                 rows=int(in_band.sum()), band_seconds=round(band_ns / 5e8, 1))

    for i, part in enumerate(route):
        if part is None:
            continue
        mask = (row_seg == i) & ~in_band
        if mask.any():
            out.append((part, s.loc[mask]))
    return out


def _attack_route(family: str, cfg: PartitionConfig) -> tuple[str | None, str | None, str]:
    """3-segment route for one attack family under the withholding config.
    seg0 is earliest, seg2 latest; temporal order is preserved when a segment is
    reassigned rather than dropped."""
    seed_w = family in cfg.seed_withheld_families
    pool_w = family in cfg.pool_withheld_families
    if seed_w and pool_w:              # novel: trusted_eval only
        return (None, None, "trusted_eval")
    if seed_w:                         # honeypot_only: early+mid -> pool
        return ("honeypot_pool", "honeypot_pool", "trusted_eval")
    if pool_w:                         # seed_only (A4): early+mid -> seed_train
        return ("seed_train", "seed_train", "trusted_eval")
    return ("seed_train", "honeypot_pool", "trusted_eval")   # seen_both


def _build_within_day(
    cleaned: dict[str, pd.DataFrame], cfg: PartitionConfig, report: LeakageReport,
) -> dict[str, list[pd.DataFrame]]:
    """Split within each (day, family) block, not each day. CICIDS2017 runs its
    attacks in sequential time blocks within a day, so a per-day temporal cut
    would route whole families to single partitions; splitting per (day, family)
    puts every family in every partition with temporal ordering intact."""
    frames: dict[str, list[pd.DataFrame]] = {p: [] for p in PARTITIONS}
    withheld: dict[str, int] = {}
    for day, df in cleaned.items():
        for (label, is_atk), grp in df.groupby([schema.LABEL, schema.BINARY_LABEL], sort=True):
            if is_atk == 0:
                split, route = cfg.benign_split, BENIGN_ROUTE
            else:
                split, route = cfg.attack_split, _attack_route(str(label), cfg)
                if route.count("trusted_eval") == 1 and route[0] is None and route[1] is None:
                    withheld[str(label)] = withheld.get(str(label), 0) + len(grp)
            for part, seg in _split_stream_temporal(
                grp, split, route, cfg, f"{day}/{label}", report
            ):
                frames[part].append(seg)
    for fam, n in withheld.items():
        report.notes.append(f"family {fam!r} withheld from seed_train AND honeypot_pool "
                            f"(novel arm): {n} rows -> trusted_eval segment only")
    return frames


# --------------------------------------------------------------------------- #
# day_split                                                                   #
# --------------------------------------------------------------------------- #
def _build_day_split(
    cleaned: dict[str, pd.DataFrame], report: LeakageReport
) -> dict[str, list[pd.DataFrame]]:
    unknown = set(cleaned) - set(DAY_TO_PARTITION)
    if unknown:
        raise ValueError(f"day_split has no assignment for day(s): {sorted(unknown)}")
    frames: dict[str, list[pd.DataFrame]] = {p: [] for p in PARTITIONS}
    for day, df in cleaned.items():
        part = DAY_TO_PARTITION[day]
        if part in BENIGN_ONLY:
            before = len(df)
            df = df[df[schema.BINARY_LABEL] == 0]
            report.notes.append(f"day_split: dropped {before - len(df)} attack rows from {part}")
        frames[part].append(df)
    return frames


# --------------------------------------------------------------------------- #
# guard (c): nearest-neighbour leakage check                                  #
# --------------------------------------------------------------------------- #
def _nn_rms(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-feature RMS distance (IQR units) from each row of *a* to nearest in *b*."""
    from sklearn.neighbors import NearestNeighbors

    nn = NearestNeighbors(n_neighbors=1).fit(b)
    dist, _ = nn.kneighbors(a)
    return dist.ravel() / np.sqrt(a.shape[1])


def _nn_leakage_check(
    data_frames: dict[str, pd.DataFrame], normalizer: Normalizer, cfg: PartitionConfig,
    report: LeakageReport,
) -> None:
    te = data_frames["trusted_eval"]
    hp = data_frames["honeypot_pool"]
    pcts = [0, 1, 5, 25, 50, 90]
    warn = False

    rng = np.random.default_rng(cfg.seed)
    for cls_name, cls_val in (("attack", 1), ("benign", 0)):
        te_c = te[te[schema.BINARY_LABEL] == cls_val].reset_index(drop=True)
        hp_c = hp[hp[schema.BINARY_LABEL] == cls_val]
        if te_c.empty or hp_c.empty:
            report.notes.append(f"NN check ({cls_name}) skipped: empty in trusted_eval or honeypot_pool")
            continue
        q = te_c
        cap = cfg.nn_check_query_sample
        if cap and len(te_c) > cap:
            q = te_c.iloc[np.sort(rng.choice(len(te_c), cap, replace=False))]
            report.notes.append(f"NN check ({cls_name}): query subsampled {len(te_c)} -> {cap}")
        rms_q = _nn_rms(normalizer.transform(q), normalizer.transform(hp_c))
        report.nn_distance[cls_name] = {
            "percentiles": {f"p{p}": float(np.percentile(rms_q, p)) for p in pcts},
            "frac_below_grid": float(np.mean(rms_q < max(cfg.near_dup_grid, 1e-6))),
            "n_query": int(len(rms_q)),
        }
        # Only the ATTACK class drives leak_warning: near-identical benign flows
        # across partitions are the normal state of real network traffic (two
        # different HTTP GETs have identical flow stats), not a memorization
        # leak. The benign distances are reported for context, not gated on.
        if cls_name == "attack" and float(np.percentile(rms_q, 5)) < cfg.nn_leak_p5_threshold:
            warn = True

        if cls_name == "attack":
            def _atk_fams(part: str) -> set[str]:
                d = data_frames[part]
                return set(d.loc[d[schema.BINARY_LABEL] == 1, schema.LABEL].unique())

            pool_fams, seed_fams = _atk_fams("honeypot_pool"), _atk_fams("seed_train")
            fam_q = q[schema.LABEL].to_numpy()
            for fam in np.unique(fam_q):
                sel = fam_q == fam
                in_s, in_p = fam in seed_fams, fam in pool_fams
                arm = ("seen_both" if in_s and in_p else "seed_only" if in_s
                       else "honeypot_only" if in_p else "novel")
                report.nn_by_family[str(fam)] = {
                    "n": int(sel.sum()),
                    "arm": arm,
                    "min_rms": float(np.min(rms_q[sel])),
                    "median_rms": float(np.median(rms_q[sel])),
                }

    report.leak_warning = warn
    logfn = log.warning if warn else log.info
    logfn("NN leakage check", strategy=cfg.strategy, leak_warning=warn,
          attack_p5=round(report.nn_distance.get("attack", {}).get("percentiles", {}).get("p5", float("nan")), 4),
          benign_p5=round(report.nn_distance.get("benign", {}).get("percentiles", {}).get("p5", float("nan")), 4))
    if warn:
        report.notes.append(
            "LEAKAGE WARNING (attack class): trusted_eval attack rows sit near "
            "honeypot_pool attack rows in feature space (5th-pct per-feature RMS below "
            "threshold). An S0 improvement may be memorization, not learning. Stop and "
            "inspect nn_by_family / nn_distance before trusting the S0 checkpoint."
        )


# --------------------------------------------------------------------------- #
# public entry point                                                          #
# --------------------------------------------------------------------------- #
def build_partitions(
    raw_by_day: dict[str, pd.DataFrame], *, config: PartitionConfig | None = None
) -> PartitionedData:
    cfg = config or PartitionConfig()
    report = LeakageReport(strategy=cfg.strategy)

    if cfg.strategy == "day_split":
        unknown = set(raw_by_day) - set(DAY_TO_PARTITION)
        if unknown:
            raise ValueError(f"day_split has no assignment for day(s): {sorted(unknown)}")

    cleaned: dict[str, pd.DataFrame] = {}
    reports: dict[str, CleaningReport] = {}
    for day, raw in raw_by_day.items():
        df, rep = clean_flows(raw, source=day)
        cleaned[day] = df
        reports[day] = rep

    all_clean = pd.concat(cleaned.values(), ignore_index=True)
    normalizer = fit_normalizer(all_clean)

    # Guard (a) runs GLOBALLY, before the split: a near-duplicate pair that spans
    # two capture days is still a memorization leak if the two rows land in
    # different partitions, and a per-day pass would never see it.
    all_clean = _remove_near_duplicates(all_clean, normalizer, cfg.near_dup_grid, report)
    cleaned = {day: g for day, g in all_clean.groupby(schema.DAY, sort=False)}

    if cfg.strategy == "within_day_temporal":
        frames = _build_within_day(cleaned, cfg, report)
    elif cfg.strategy == "day_split":
        frames = _build_day_split(cleaned, report)
    else:  # pragma: no cover
        raise ValueError(f"unknown strategy: {cfg.strategy!r}")

    out: dict[str, pd.DataFrame] = {}
    for part in PARTITIONS:
        if not frames[part]:
            raise ValueError(f"partition {part!r} received no rows (strategy={cfg.strategy})")
        out[part] = pd.concat(frames[part], ignore_index=True)

    if cfg.strategy == "within_day_temporal" and (
        cfg.pool_withheld_families or cfg.seed_withheld_families
    ):
        log.info("family withholding applied", pool_withheld=list(cfg.pool_withheld_families),
                 seed_withheld=list(cfg.seed_withheld_families))

    result = PartitionedData(
        frames=out, cleaning=reports, leakage=report, config=cfg, normalizer=normalizer
    )
    assert_disjoint(result)
    _nn_leakage_check(out, normalizer, cfg, report)
    return result


def assert_disjoint(data: PartitionedData) -> dict[str, int]:
    """Assert the four partitions share no row content, and — per strategy —
    no capture day (day_split) or overlapping segment time ranges
    (within_day_temporal). Raises ``AssertionError`` on any hard overlap."""
    frames = data.frames

    hashes = {p: set(_row_hashes(df)) for p, df in frames.items()}
    overlaps: dict[str, int] = {}
    for a in PARTITIONS:
        for b in PARTITIONS:
            if a < b:
                common = hashes[a] & hashes[b]
                overlaps[f"{a}|{b}"] = len(common)
                if common:
                    raise AssertionError(f"row-content overlap between {a} and {b}: {len(common)}")

    if data.config.strategy == "day_split":
        day_sets = {p: set(df[schema.DAY].unique()) for p, df in frames.items()}
        for a in PARTITIONS:
            for b in PARTITIONS:
                if a < b and day_sets[a] & day_sets[b]:
                    raise AssertionError(f"day overlap {a}/{b}: {sorted(day_sets[a] & day_sets[b])}")
    else:
        # within_day_temporal: for each (day, family) block the segments must be
        # time-ordered across partitions with no overlap (the guard band ensures
        # a gap). Check max(earlier) < min(later) along the partition ordering,
        # which differs by class (benign visits prod_benign, attack does not).
        benign_order = {"seed_train": 0, "prod_benign": 1, "honeypot_pool": 2, "trusted_eval": 3}
        attack_order = {"seed_train": 0, "honeypot_pool": 1, "trusted_eval": 2}
        # (day, label) -> list of (order, min_ts, max_ts); built per-partition so
        # the full dataset is never concatenated into one frame.
        spans: dict[tuple, list] = {}
        for part, df in frames.items():
            gb = df.groupby([schema.DAY, schema.LABEL], sort=False)
            gmin, gmax = gb[schema.TIMESTAMP].min(), gb[schema.TIMESTAMP].max()
            is_benign = gb[schema.BINARY_LABEL].first()
            for k, lo in gmin.items():
                order = benign_order if is_benign[k] == 0 else attack_order
                spans.setdefault(k, []).append((order[part], lo, gmax[k]))
        for (day, label), bounds in spans.items():
            bounds.sort()
            for (o1, _, hi1), (o2, lo2, _) in zip(bounds, bounds[1:], strict=False):
                if o1 != o2 and hi1 >= lo2:
                    raise AssertionError(f"time overlap in ({day}, {label}): {hi1} >= {lo2}")

    log.info("partition disjointness verified", strategy=data.config.strategy,
             pair_overlaps=overlaps)
    return overlaps
