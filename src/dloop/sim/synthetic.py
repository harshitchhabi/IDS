"""Synthetic flow generator — the no-download fallback for Phase 0.

CLAUDE.md: "The entire pipeline must run on synthetic data with no external
downloads. Every phase ships a synthetic fallback."

The generator emits data in *raw CICIDS2017 shape* — original CICFlowMeter
column names, the ``' Label'`` column with its leading space, capture-day tag —
and deliberately injects the same corruption classes the real dataset carries
(non-finite rates, NaN cells, negative durations, duplicate rows) so the
cleaning pipeline and its drop report are exercised end-to-end without the CSVs.

Class geometry is intentionally well-separated: S0 (the clean loop) must be able
to improve the detector, which is only meaningful if the base classes are
learnable. Benign-mimicry (A1) lives in the adversary code, not here.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.logging_config import get_logger

log = get_logger("sim.synthetic")

# Reverse of the cleaning map: canonical name -> raw CICIDS2017 column name.
_CANON_TO_RAW = {v: k for k, v in schema.CICIDS_COLUMN_MAP.items()}

# Base benign profile: (mean, sigma) of a log-normal for each canonical feature,
# in "natural" units. Chosen to look roughly like short interactive/browsing
# flows. Flag counts are overridden to Poisson below.
_BENIGN: dict[str, tuple[float, float]] = {
    "flow_duration": (5.0e6, 1.1),      # microseconds
    "fwd_packets": (12.0, 0.9),
    "bwd_packets": (10.0, 0.9),
    "fwd_bytes": (1.2e3, 1.0),
    "bwd_bytes": (4.0e3, 1.1),
    "fwd_pkt_len_max": (400.0, 0.7),
    "fwd_pkt_len_min": (40.0, 0.5),
    "fwd_pkt_len_mean": (120.0, 0.6),
    "bwd_pkt_len_max": (900.0, 0.6),
    "bwd_pkt_len_min": (40.0, 0.5),
    "bwd_pkt_len_mean": (350.0, 0.6),
    "flow_iat_mean": (4.0e5, 1.0),
    "flow_iat_std": (5.0e5, 1.0),
    "flow_iat_max": (1.5e6, 1.0),
    "flow_iat_min": (5.0e3, 1.2),
    "fwd_iat_mean": (6.0e5, 1.0),
    "bwd_iat_mean": (6.0e5, 1.0),
    "down_up_ratio": (1.4, 0.5),
    "pkt_size_avg": (300.0, 0.6),
}
_BENIGN_FLAGS = {"syn_flag_count": 1.0, "psh_flag_count": 3.0, "ack_flag_count": 15.0}

# Attack profiles: multiplicative overrides on the benign (mean, sigma) pairs,
# plus flag-count means. Everything else inherits the benign profile.
#
# ``burst`` places the family on the day's timeline, which decides how the
# within-day temporal split routes it (attack cuts at 40% / 80% of the window):
#   "sustained"        - long campaign spanning the window; straddles both cuts,
#                        so the family lands in seed_train AND the adversary pool
#                        AND trusted_eval  -> eval arm "seen_both".
#   "brief_early"       - short burst near the start; seed_train only (not scored).
#   "brief_late"        - short burst near the end; trusted_eval only -> "novel".
#   "split_early_late"  - two short bursts, one before the first cut and one
#                        after the last, nothing in the middle: seed_train AND
#                        trusted_eval but NOT the adversary pool -> eval arm
#                        "seed_only", the baseline for A4's controlled withholding.
@dataclass(frozen=True)
class _AttackProfile:
    label: str
    scale: dict[str, float] = field(default_factory=dict)
    flags: dict[str, float] = field(default_factory=dict)
    burst: str = "sustained"


_ATTACKS: dict[str, list[_AttackProfile]] = {
    "tuesday": [
        _AttackProfile("SSH-Patator", {"flow_duration": 0.6, "fwd_packets": 1.8,
                                       "bwd_packets": 1.8, "fwd_bytes": 2.5},
                       {"syn_flag_count": 6.0, "ack_flag_count": 40.0}, burst="split_early_late"),
        _AttackProfile("FTP-Patator", {"flow_duration": 0.4, "fwd_packets": 2.2,
                                       "fwd_bytes": 1.6, "bwd_bytes": 0.3},
                       {"syn_flag_count": 6.0}, burst="brief_early"),
    ],
    "wednesday": [
        _AttackProfile("DoS Hulk", {"flow_duration": 0.15, "fwd_packets": 0.4,
                                    "bwd_packets": 0.2, "fwd_bytes": 4.0,
                                    "pkt_size_avg": 3.0, "flow_iat_min": 0.05},
                       {"syn_flag_count": 2.0, "psh_flag_count": 8.0, "ack_flag_count": 2.0},
                       burst="sustained"),
    ],
    "thursday": [
        _AttackProfile("Web Attack Brute Force", {"flow_duration": 2.5, "fwd_bytes": 5.0,
                                                  "fwd_pkt_len_max": 4.0, "fwd_packets": 2.0},
                       {"psh_flag_count": 12.0}, burst="sustained"),
        _AttackProfile("Infiltration", {"flow_duration": 6.0, "bwd_bytes": 20.0,
                                        "bwd_packets": 8.0, "down_up_ratio": 5.0},
                       {"ack_flag_count": 80.0}, burst="brief_late"),
    ],
    "friday": [
        _AttackProfile("Bot", {"flow_duration": 0.5, "fwd_packets": 0.5, "bwd_packets": 0.5,
                               "fwd_bytes": 0.4, "flow_iat_std": 0.2},
                       {"psh_flag_count": 1.0, "ack_flag_count": 6.0}, burst="brief_late"),
        _AttackProfile("PortScan", {"flow_duration": 0.02, "fwd_packets": 0.15,
                                    "bwd_packets": 0.1, "fwd_bytes": 0.05, "bwd_bytes": 0.05,
                                    "pkt_size_avg": 0.2, "flow_iat_mean": 0.02},
                       {"syn_flag_count": 12.0, "ack_flag_count": 0.0, "psh_flag_count": 0.0},
                       burst="sustained"),
        _AttackProfile("DDoS", {"flow_duration": 0.3, "fwd_packets": 6.0, "bwd_packets": 0.3,
                                "fwd_bytes": 8.0, "pkt_size_avg": 2.0},
                       {"syn_flag_count": 10.0, "psh_flag_count": 4.0}, burst="sustained"),
    ],
}

DAYS: tuple[str, ...] = ("monday", "tuesday", "wednesday", "thursday", "friday")


@dataclass
class SyntheticConfig:
    seed: int = 20250903
    # Volumes sized so the two-class adversary pool reaches ~20k rows and A1
    # poison ratios up to 50% are reachable with fresh (not resampled) rows.
    benign_per_day: int = 14000
    attack_per_class: int = 1400
    # Capture window each day (flows get timestamps inside it so the within-day
    # temporal split has a real timeline to cut).
    first_date: str = "2017-07-03"       # a Monday
    window_start_hour: int = 9
    window_hours: float = 8.0
    brief_burst_frac: float = 0.12       # fraction of the window a brief burst spans
    # Corruption injection (fraction of each day's rows), mirrors CICIDS2017.
    frac_nonfinite_rate: float = 0.010   # zero-duration -> Inf rate columns
    frac_nan_cell: float = 0.004         # sporadic missing feature
    frac_negative: float = 0.002         # negative Flow Duration artifact
    frac_duplicate: float = 0.015        # exact duplicate rows
    # Guard-(a) self-test: a fraction of each sustained attack family's rows are
    # near-identical copies of a few centroids, mimicking an automated tool that
    # emits near-byte-identical flows. The partition's near-duplicate guard must
    # remove these before splitting. Set 0 to disable.
    fingerprint_tight_frac: float = 0.03
    fingerprint_centroids: int = 6


def _sample_class(rng: np.random.Generator, n: int, profile: _AttackProfile | None) -> pd.DataFrame:
    cols: dict[str, np.ndarray] = {}
    scale = profile.scale if profile else {}
    for feat, (mean, sigma) in _BENIGN.items():
        m = mean * scale.get(feat, 1.0)
        # log-normal with the given natural-scale mean
        mu = np.log(max(m, 1e-9)) - 0.5 * sigma**2
        cols[feat] = rng.lognormal(mu, sigma, n)

    flags = dict(_BENIGN_FLAGS)
    if profile:
        flags.update(profile.flags)
    for feat, lam in flags.items():
        cols[feat] = rng.poisson(max(lam, 0.0), n).astype("float64")

    df = pd.DataFrame(cols)
    # Enforce simple physical consistency the profiles don't guarantee.
    df["flow_pkts_per_s"] = (df["fwd_packets"] + df["bwd_packets"]) / (df["flow_duration"] / 1e6)
    df["flow_bytes_per_s"] = (df["fwd_bytes"] + df["bwd_bytes"]) / (df["flow_duration"] / 1e6)
    df["fwd_pkt_len_min"] = np.minimum(df["fwd_pkt_len_min"], df["fwd_pkt_len_max"])
    df["bwd_pkt_len_min"] = np.minimum(df["bwd_pkt_len_min"], df["bwd_pkt_len_max"])
    df["flow_iat_min"] = np.minimum(df["flow_iat_min"], df["flow_iat_max"])
    df[schema.LABEL] = profile.label if profile else schema.BENIGN_LABEL
    return df[[*schema.CANONICAL_FEATURES, schema.LABEL]]


def _inject_corruption(rng: np.random.Generator, df: pd.DataFrame, cfg: SyntheticConfig) -> pd.DataFrame:
    n = len(df)
    feats = list(schema.CANONICAL_FEATURES)

    def pick(frac: float) -> np.ndarray:
        return rng.choice(n, size=int(n * frac), replace=False)

    for i in pick(cfg.frac_nonfinite_rate):
        df.iloc[i, df.columns.get_loc("flow_duration")] = 0.0
        df.iloc[i, df.columns.get_loc("flow_bytes_per_s")] = np.inf
        df.iloc[i, df.columns.get_loc("flow_pkts_per_s")] = np.inf

    for i in pick(cfg.frac_nan_cell):
        df.iloc[i, df.columns.get_loc(rng.choice(feats))] = np.nan

    for i in pick(cfg.frac_negative):
        df.iloc[i, df.columns.get_loc("flow_duration")] *= -1.0

    dups = df.iloc[pick(cfg.frac_duplicate)].copy()
    return pd.concat([df, dups], ignore_index=True)


def _to_raw_cicids(df: pd.DataFrame) -> pd.DataFrame:
    """Rename canonical columns back to raw CICIDS2017 names + ``' Label'`` /
    ``' Timestamp'`` (leading spaces, as the real CSVs carry them)."""
    rename = {c: _CANON_TO_RAW[c] for c in schema.CANONICAL_FEATURES}
    rename[schema.LABEL] = schema.CICIDS_LABEL_COLUMN
    rename[schema.TIMESTAMP] = schema.CICIDS_TIMESTAMP_COLUMN
    return df.rename(columns=rename)


def _burst_offsets_s(
    rng: np.random.Generator, n: int, burst: str, window_s: float, brief_frac: float
) -> np.ndarray:
    """Sorted second-offsets into the day's window for one attack family."""
    if burst == "sustained":
        lo = rng.uniform(0.05, 0.15) * window_s
        hi = rng.uniform(0.88, 1.00) * window_s
    elif burst == "brief_early":
        lo = rng.uniform(0.0, 0.05) * window_s
        hi = lo + brief_frac * window_s
    elif burst == "brief_late":
        hi = rng.uniform(0.95, 1.00) * window_s
        lo = hi - brief_frac * window_s
    elif burst == "split_early_late":
        # two short bursts: one in the first ~5%, one in the last ~5%, nothing
        # in the middle -> seed_train + trusted_eval but not the adversary pool.
        n_early = n // 2
        early = rng.uniform(0.0, brief_frac, n_early) * window_s
        late = (1.0 - brief_frac + rng.uniform(0.0, brief_frac, n - n_early)) * window_s
        return np.sort(np.concatenate([early, late]))
    else:  # pragma: no cover
        raise ValueError(f"unknown burst type: {burst!r}")
    return np.sort(rng.uniform(lo, hi, n))


def _apply_fingerprint_tightness(
    rng: np.random.Generator, atk: pd.DataFrame, cfg: SyntheticConfig
) -> pd.DataFrame:
    """Overwrite a fraction of rows with near-identical copies of a few
    centroids — an automated tool emitting near-byte-identical flows. The
    partition's near-duplicate guard (a) must remove these before splitting."""
    n = len(atk)
    k = min(cfg.fingerprint_centroids, n)
    n_tight = int(n * cfg.fingerprint_tight_frac)
    if n_tight < 2 or k < 1:
        return atk
    feats = list(schema.CANONICAL_FEATURES)
    centroids = atk[feats].to_numpy("float64")[rng.choice(n, k, replace=False)]
    rows = rng.choice(n, n_tight, replace=False)
    pick = rng.integers(0, k, n_tight)
    jitter = 1.0 + rng.normal(0.0, 1e-4, (n_tight, len(feats)))
    atk = atk.copy()
    atk.iloc[rows, [atk.columns.get_loc(f) for f in feats]] = centroids[pick] * jitter
    return atk


def generate_raw_by_day(cfg: SyntheticConfig | None = None) -> dict[str, pd.DataFrame]:
    """Return ``{day: raw CICIDS-shaped frame}`` — the synthetic drop-in for
    :func:`dloop.sim.cicids.load_raw_by_day`."""
    cfg = cfg or SyntheticConfig()
    root = np.random.default_rng(cfg.seed)
    window_s = cfg.window_hours * 3600.0
    out: dict[str, pd.DataFrame] = {}

    for d, day in enumerate(DAYS):
        rng = np.random.default_rng(root.integers(0, 2**63))
        base = pd.Timestamp(cfg.first_date) + _dt.timedelta(
            days=d, hours=cfg.window_start_hour
        )

        benign = _sample_class(rng, cfg.benign_per_day, None)
        benign[schema.TIMESTAMP] = base + pd.to_timedelta(
            np.sort(rng.uniform(0.0, window_s, len(benign))), unit="s"
        )
        parts = [benign]
        for profile in _ATTACKS.get(day, []):
            atk = _sample_class(rng, cfg.attack_per_class, profile)
            if profile.burst == "sustained":
                atk = _apply_fingerprint_tightness(rng, atk, cfg)
            atk[schema.TIMESTAMP] = base + pd.to_timedelta(
                _burst_offsets_s(rng, len(atk), profile.burst, window_s, cfg.brief_burst_frac),
                unit="s",
            )
            parts.append(atk)

        df = pd.concat(parts, ignore_index=True)
        df = df.sample(frac=1.0, random_state=int(rng.integers(0, 2**31))).reset_index(drop=True)
        df = _inject_corruption(rng, df, cfg)
        df[schema.DAY] = day
        raw = _to_raw_cicids(df)
        out[day] = raw
        log.info("generated synthetic day", day=day, rows=len(raw),
                 window=(str(base), str(base + _dt.timedelta(seconds=window_s))),
                 classes=sorted(df[schema.LABEL].unique()))
    return out
