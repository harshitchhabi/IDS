"""Four-way partition of the Phase 0 dataset, with temporal-leakage guards.

CLAUDE.md, Phase 0: four **disjoint** sets — ``seed_train``, ``prod_benign``,
``honeypot_pool``, ``trusted_eval`` — split to avoid temporal leakage.

Two strategies (``PartitionConfig.strategy``):

``within_day_temporal`` *(default)*
    Split each capture day along its own timeline. The literature's claim for
    honeypot auto-labeling is *contemporaneous and within-campaign* — the decoy
    sees the current campaign and the detector gets better at catching it — so
    the honeypot pool and the eval set must be allowed to contain the same
    attack families, separated only in time. Per day, the benign and attack
    flow streams are each sorted by timestamp and cut by cumulative fraction:

      * benign  -> ``seed_train`` (early) | ``prod_benign`` (mid) | ``trusted_eval`` (late)
      * attack  -> ``seed_train`` (early) | ``honeypot_pool`` (mid) | ``trusted_eval`` (late)

``day_split``
    Whole days routed to whole partitions (:data:`DAY_TO_PARTITION`). Retained
    as a robustness check: it withholds every attack family from the honeypot
    maximally *by construction*, which both makes A4 (fingerprint-and-split) a
    partition artifact rather than a manipulable variable and turns the S0
    checkpoint into a cross-family-generalization test the literature never
    claims. Useful only as a contrast to the default.

Leakage guards (``within_day_temporal``), all reported, none silently passed —
because most CICIDS2017 attacks are single automated-tool bursts and splitting
one burst by time drops near-identical rows into both ``honeypot_pool`` and
``trusted_eval``, which would let S0 "improve" by memorizing a tool fingerprint
and *false-pass* the checkpoint:

  a. Hard de-duplication before splitting — exact duplicates (in
     :mod:`dloop.features.cleaning`) plus near-duplicates here, snapped to a
     grid in normalized feature space. Counts logged per day per class.
  b. A temporal guard band: rows within ``boundary_buffer_seconds`` of an
     internal cut time are dropped so a burst cannot straddle the cut.
  c. Nearest-neighbour distance, in normalized feature space, from every
     ``trusted_eval`` attack flow to its closest ``honeypot_pool`` attack flow.
     The distribution is reported; concentration near zero means the partition
     is leaking and any S0 gain is memorization — :class:`LeakageReport` flags
     it and callers must stop.
"""

from __future__ import annotations

import hashlib
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

    # Guard (b): temporal guard band around each internal cut.
    boundary_buffer_seconds: float = 300.0
    max_buffer_frac: float = 0.25  # shrink the band rather than exceed this per stream

    # Guard (a): near-duplicate grid cell size in normalized (log-IQR) units.
    # 0 disables. ~0.02 == 2% of an IQR; larger removes more aggressively.
    near_dup_grid: float = 0.02

    # Guard (c): flag leakage if the 5th-percentile normalized NN distance
    # (per-feature RMS) from trusted_eval attacks to honeypot_pool attacks is
    # below this.
    nn_leak_p5_threshold: float = 0.25

    # A4 selective disclosure: attack families withheld from honeypot_pool.
    a4_withheld_families: tuple[str, ...] = ()

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
    buffer_rows_removed: dict[str, int] = field(default_factory=dict)            # "day/class" -> n
    a4_withheld_removed: dict[str, int] = field(default_factory=dict)            # family -> n
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

    def eval_family_split(self) -> dict[str, list[str]]:
        """trusted_eval attack families, in three arms by where they appear.

        S0's TPR must be reported broken out these three ways every round:

        * ``seen_both`` — in seed_train AND the adversary pool. The loop may
          improve TPR here.
        * ``seed_only`` — in seed_train, withheld from the adversary pool. This
          is A4's controlled measurement arm and must never be collapsed into
          ``novel``.
        * ``novel`` — in neither. Supervised models are expected at ~0 TPR.
        """
        fam = self.families_by_partition()
        te, seed, pool = fam["trusted_eval"], fam["seed_train"], fam["honeypot_pool"]
        return {
            "seen_both": sorted(f for f in te if f in seed and f in pool),
            "seed_only": sorted(f for f in te if f in seed and f not in pool),
            "novel": sorted(f for f in te if f not in seed and f not in pool),
        }

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
def _row_hashes(df: pd.DataFrame) -> pd.Series:
    cols = [*schema.CANONICAL_FEATURES, schema.LABEL]
    packed = df[cols].round(6).astype(str).agg("|".join, axis=1)
    return packed.map(lambda s: hashlib.blake2b(s.encode(), digest_size=16).hexdigest())


# --------------------------------------------------------------------------- #
# guard (a): near-duplicate removal                                           #
# --------------------------------------------------------------------------- #
def _remove_near_duplicates(
    day_df: pd.DataFrame, day: str, normalizer: Normalizer, grid: float, report: LeakageReport
) -> pd.DataFrame:
    """Drop rows within ``grid`` (per-feature RMS, normalized units) of a kept
    row of the same label. Radius-based, not grid-cell — grid-cell rounding lets
    a near-duplicate pair straddle a cell boundary and survive, which is exactly
    the leak this guard exists to stop."""
    if grid <= 0 or len(day_df) < 2:
        return day_df
    from sklearn.neighbors import NearestNeighbors

    x = normalizer.transform(day_df)
    labels = day_df[schema.LABEL].to_numpy()
    radius = grid * np.sqrt(x.shape[1])  # per-feature RMS -> total L2
    graph = NearestNeighbors(radius=radius).fit(x).radius_neighbors_graph(x, mode="connectivity")

    kept: set[int] = set()
    drop = np.zeros(len(day_df), dtype=bool)
    for i in range(len(day_df)):
        nbrs = graph.indices[graph.indptr[i] : graph.indptr[i + 1]]
        if any(j in kept and labels[j] == labels[i] for j in nbrs):
            drop[i] = True
        else:
            kept.add(i)

    if drop.any():
        by_class = {
            str(k): int(v) for k, v in day_df.loc[drop, schema.LABEL].value_counts().items()
        }
        report.near_dups_removed[day] = by_class
        log.info("near-duplicate rows removed", day=day, total=int(drop.sum()),
                 by_class=by_class, grid=grid)
    return day_df.loc[~drop]


# --------------------------------------------------------------------------- #
# within_day_temporal split                                                   #
# --------------------------------------------------------------------------- #
def _split_stream_temporal(
    stream: pd.DataFrame,
    split: tuple[float, ...],
    route: tuple[str, ...],
    cfg: PartitionConfig,
    tag: str,
    report: LeakageReport,
) -> dict[str, pd.DataFrame]:
    """Cut one time-sorted class stream into ``len(route)`` segments, dropping a
    temporal guard band around each internal cut."""
    out: dict[str, pd.DataFrame] = {}
    if stream.empty:
        return out
    s = stream.sort_values(schema.TIMESTAMP, kind="stable")
    ts = s[schema.TIMESTAMP].to_numpy("datetime64[ns]")
    t_span_s = max((ts[-1] - ts[0]) / np.timedelta64(1, "s"), 1e-9)

    # internal cut times at the cumulative fractions (all but the last segment)
    cum = np.cumsum(split)[:-1]
    cut_times = [ts[0] + np.timedelta64(int(f * t_span_s * 1e9), "ns") for f in cum]

    band_ns = int(cfg.boundary_buffer_seconds * 1e9 / 2)
    in_band = np.zeros(len(ts), dtype=bool)
    # cap band so it never exceeds max_buffer_frac of the stream
    while band_ns > 0:
        in_band = np.zeros(len(ts), dtype=bool)
        for ct in cut_times:
            in_band |= (ts >= ct - np.timedelta64(band_ns, "ns")) & (
                ts < ct + np.timedelta64(band_ns, "ns")
            )
        if in_band.mean() <= cfg.max_buffer_frac:
            break
        band_ns //= 2
    if in_band.any():
        key = f"{tag}"
        report.buffer_rows_removed[key] = report.buffer_rows_removed.get(key, 0) + int(in_band.sum())
        log.info("temporal guard band dropped rows", stream=tag, rows=int(in_band.sum()),
                 band_seconds=round(band_ns / 5e8, 1))

    seg_idx = np.digitize(
        ts.astype("int64"), [c.astype("datetime64[ns]").astype("int64") for c in cut_times]
    )
    for i, part in enumerate(route):
        mask = (seg_idx == i) & ~in_band
        if mask.any():
            out[part] = s.loc[mask]
    return out


def _build_within_day(
    cleaned: dict[str, pd.DataFrame], cfg: PartitionConfig, normalizer: Normalizer,
    report: LeakageReport,
) -> dict[str, list[pd.DataFrame]]:
    frames: dict[str, list[pd.DataFrame]] = {p: [] for p in PARTITIONS}
    for day, df in cleaned.items():
        df = _remove_near_duplicates(df, day, normalizer, cfg.near_dup_grid, report)
        benign = df[df[schema.BINARY_LABEL] == 0]
        attack = df[df[schema.BINARY_LABEL] == 1]
        for part, seg in _split_stream_temporal(
            benign, cfg.benign_split, BENIGN_ROUTE, cfg, f"{day}/benign", report
        ).items():
            frames[part].append(seg)
        for part, seg in _split_stream_temporal(
            attack, cfg.attack_split, ATTACK_ROUTE, cfg, f"{day}/attack", report
        ).items():
            frames[part].append(seg)
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

    for cls_name, cls_val in (("attack", 1), ("benign", 0)):
        te_c = te[te[schema.BINARY_LABEL] == cls_val]
        hp_c = hp[hp[schema.BINARY_LABEL] == cls_val]
        if te_c.empty or hp_c.empty:
            report.notes.append(f"NN check ({cls_name}) skipped: empty in trusted_eval or honeypot_pool")
            continue
        rms = _nn_rms(normalizer.transform(te_c), normalizer.transform(hp_c))
        report.nn_distance[cls_name] = {
            "percentiles": {f"p{p}": float(np.percentile(rms, p)) for p in pcts},
            "frac_below_grid": float(np.mean(rms < max(cfg.near_dup_grid, 1e-6))),
        }
        if float(np.percentile(rms, 5)) < cfg.nn_leak_p5_threshold:
            warn = True

        if cls_name == "attack":
            pool_fams = set(hp_c[schema.LABEL].unique())
            seed_fams = set(
                data_frames["seed_train"].loc[
                    data_frames["seed_train"][schema.BINARY_LABEL] == 1, schema.LABEL
                ].unique()
            )
            te_c = te_c.reset_index(drop=True)
            for fam, idx in te_c.groupby(schema.LABEL).groups.items():
                pos = np.asarray(idx)
                arm = ("seen_both" if fam in pool_fams and fam in seed_fams
                       else "seed_only" if fam in seed_fams
                       else "novel")
                report.nn_by_family[str(fam)] = {
                    "n": int(len(pos)),
                    "arm": arm,
                    "min_rms": float(np.min(rms[pos])),
                    "median_rms": float(np.median(rms[pos])),
                }

    report.leak_warning = warn
    logfn = log.warning if warn else log.info
    logfn("NN leakage check", strategy=cfg.strategy, leak_warning=warn,
          attack_p5=round(report.nn_distance.get("attack", {}).get("percentiles", {}).get("p5", float("nan")), 4),
          benign_p5=round(report.nn_distance.get("benign", {}).get("percentiles", {}).get("p5", float("nan")), 4))
    if warn:
        report.notes.append(
            "LEAKAGE WARNING: trusted_eval rows sit near honeypot_pool rows in feature "
            "space (5th-pct per-feature RMS below threshold). An S0 improvement may be "
            "memorization, not learning. Stop and inspect nn_by_family / nn_distance "
            "before trusting the S0 checkpoint."
        )


# --------------------------------------------------------------------------- #
# public entry point                                                          #
# --------------------------------------------------------------------------- #
def build_partitions(
    raw_by_day: dict[str, pd.DataFrame], *, config: PartitionConfig | None = None
) -> PartitionedData:
    cfg = config or PartitionConfig()
    report = LeakageReport(strategy=cfg.strategy)

    cleaned: dict[str, pd.DataFrame] = {}
    reports: dict[str, CleaningReport] = {}
    for day, raw in raw_by_day.items():
        df, rep = clean_flows(raw, source=day)
        cleaned[day] = df
        reports[day] = rep

    normalizer = fit_normalizer(pd.concat(cleaned.values(), ignore_index=True))

    if cfg.strategy == "within_day_temporal":
        frames = _build_within_day(cleaned, cfg, normalizer, report)
    elif cfg.strategy == "day_split":
        frames = _build_day_split(cleaned, report)
    else:  # pragma: no cover
        raise ValueError(f"unknown strategy: {cfg.strategy!r}")

    out: dict[str, pd.DataFrame] = {}
    for part in PARTITIONS:
        if not frames[part]:
            raise ValueError(f"partition {part!r} received no rows (strategy={cfg.strategy})")
        out[part] = pd.concat(frames[part], ignore_index=True)

    # A4 selective disclosure: withhold families from the honeypot pool.
    if cfg.a4_withheld_families:
        hp = out["honeypot_pool"]
        mask = hp[schema.LABEL].isin(cfg.a4_withheld_families)
        report.a4_withheld_removed = {
            str(k): int(v) for k, v in hp.loc[mask, schema.LABEL].value_counts().items()
        }
        out["honeypot_pool"] = hp.loc[~mask].reset_index(drop=True)
        log.info("A4: withheld families from honeypot_pool", removed=report.a4_withheld_removed)

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
        # within_day_temporal: for each day+class stream the segments must be
        # time-ordered across partitions with no overlap (the guard band ensures
        # a gap). Check max(earlier) < min(later).
        for day in {d for df in frames.values() for d in df[schema.DAY].unique()}:
            for is_attack, route in ((0, BENIGN_ROUTE), (1, ATTACK_ROUTE)):
                bounds = []
                for part in route:
                    df = frames[part]
                    seg = df[(df[schema.DAY] == day) & (df[schema.BINARY_LABEL] == is_attack)]
                    if not seg.empty:
                        bounds.append((seg[schema.TIMESTAMP].min(), seg[schema.TIMESTAMP].max()))
                for (lo1, hi1), (lo2, hi2) in zip(bounds, bounds[1:], strict=False):
                    if hi1 >= lo2:
                        raise AssertionError(
                            f"time overlap in {day} attack={is_attack}: {hi1} >= {lo2}"
                        )

    log.info("partition disjointness verified", strategy=data.config.strategy,
             pair_overlaps=overlaps)
    return overlaps
