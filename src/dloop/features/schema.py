"""Feature schema — the single source of truth for flow features.

Every part of the system (Phase 0 simulator, Phase 1 nfstream sensor, every
model, every adversary) agrees on the feature vector *here*. CICIDS2017 columns
and, later, nfstream fields are mapped onto these canonical names so downstream
code never sees a raw dataset column.

The canonical names are deliberately close to nfstream's bidirectional-flow
statistics so the Phase 1 sensor mapping is mechanical.
"""

from __future__ import annotations

import pandas as pd

# Bump when CANONICAL_FEATURES changes in a way that invalidates a trained
# model or a persisted feature batch. Written into every model metadata sidecar.
SCHEMA_VERSION = "1"

# Ordered canonical feature vector. Order is part of the contract: models and
# adversary batches index columns positionally in places.
CANONICAL_FEATURES: tuple[str, ...] = (
    "flow_duration",
    "fwd_packets",
    "bwd_packets",
    "fwd_bytes",
    "bwd_bytes",
    "fwd_pkt_len_max",
    "fwd_pkt_len_min",
    "fwd_pkt_len_mean",
    "bwd_pkt_len_max",
    "bwd_pkt_len_min",
    "bwd_pkt_len_mean",
    "flow_bytes_per_s",
    "flow_pkts_per_s",
    "flow_iat_mean",
    "flow_iat_std",
    "flow_iat_max",
    "flow_iat_min",
    "fwd_iat_mean",
    "bwd_iat_mean",
    "syn_flag_count",
    "psh_flag_count",
    "ack_flag_count",
    "down_up_ratio",
    "pkt_size_avg",
)

# Extension features: NetFlow v2 magnitudes with no CICFlowMeter analogue (Phase R
# item R3, DECISIONS.md §31). A dataset's feature set is its canonical features (in
# canonical order, cost features first) followed by any of these, in this order.
# Names are the raw NetFlow v2 field, lower-cased, prefixed ``nf_``.
NETFLOW_V2_EXTENSION_FEATURES: tuple[str, ...] = tuple("nf_" + c.lower() for c in (
    "DURATION_IN", "DURATION_OUT", "MIN_TTL", "MAX_TTL", "LONGEST_FLOW_PKT", "SHORTEST_FLOW_PKT",
    "MIN_IP_PKT_LEN", "MAX_IP_PKT_LEN", "SRC_TO_DST_SECOND_BYTES", "DST_TO_SRC_SECOND_BYTES",
    "RETRANSMITTED_IN_BYTES", "RETRANSMITTED_IN_PKTS", "RETRANSMITTED_OUT_BYTES",
    "RETRANSMITTED_OUT_PKTS", "SRC_TO_DST_AVG_THROUGHPUT", "DST_TO_SRC_AVG_THROUGHPUT",
    "NUM_PKTS_UP_TO_128_BYTES", "NUM_PKTS_128_TO_256_BYTES", "NUM_PKTS_256_TO_512_BYTES",
    "NUM_PKTS_512_TO_1024_BYTES", "NUM_PKTS_1024_TO_1514_BYTES", "TCP_WIN_MAX_IN",
    "TCP_WIN_MAX_OUT", "DNS_TTL_ANSWER",
))
EXTENSION_FEATURES: tuple[str, ...] = NETFLOW_V2_EXTENSION_FEATURES

# The two columns CICIDS2017 is documented to fill with NaN / +-Inf: they are
# byte/packet counts divided by a flow duration that can be zero.
RATE_FEATURES: frozenset[str] = frozenset({"flow_bytes_per_s", "flow_pkts_per_s"})

# Every canonical feature is a physically non-negative quantity (a duration, a
# count, a length, an inter-arrival time, a ratio). A negative value is a known
# CICIDS2017 artifact (e.g. negative "Flow Duration") and marks a corrupt row.
# The extension features are magnitudes too (counts, lengths, TTLs, window sizes).
NONNEGATIVE_FEATURES: frozenset[str] = frozenset(CANONICAL_FEATURES) | frozenset(EXTENSION_FEATURES)

LABEL = "label"          # canonical fine-grained label, e.g. "BENIGN", "PortScan"
BINARY_LABEL = "is_attack"  # canonical 0/1 target
DAY = "day"              # capture-day tag
TIMESTAMP = "timestamp"  # flow start time; drives the within-day temporal partition

# Non-feature metadata columns carried alongside the feature vector.
META_COLUMNS: tuple[str, ...] = (LABEL, BINARY_LABEL, DAY, TIMESTAMP)

BENIGN_LABEL = "BENIGN"

# Raw CICIDS2017 columns — literally " Label" / " Timestamp" with a leading space.
CICIDS_LABEL_COLUMN = " Label"
CICIDS_TIMESTAMP_COLUMN = " Timestamp"

# Map whitespace-stripped CICIDS2017 (CICFlowMeter) column names -> canonical.
CICIDS_COLUMN_MAP: dict[str, str] = {
    "Flow Duration": "flow_duration",
    "Total Fwd Packets": "fwd_packets",
    "Total Backward Packets": "bwd_packets",
    "Total Length of Fwd Packets": "fwd_bytes",
    "Total Length of Bwd Packets": "bwd_bytes",
    "Fwd Packet Length Max": "fwd_pkt_len_max",
    "Fwd Packet Length Min": "fwd_pkt_len_min",
    "Fwd Packet Length Mean": "fwd_pkt_len_mean",
    "Bwd Packet Length Max": "bwd_pkt_len_max",
    "Bwd Packet Length Min": "bwd_pkt_len_min",
    "Bwd Packet Length Mean": "bwd_pkt_len_mean",
    "Flow Bytes/s": "flow_bytes_per_s",
    "Flow Packets/s": "flow_pkts_per_s",
    "Flow IAT Mean": "flow_iat_mean",
    "Flow IAT Std": "flow_iat_std",
    "Flow IAT Max": "flow_iat_max",
    "Flow IAT Min": "flow_iat_min",
    "Fwd IAT Mean": "fwd_iat_mean",
    "Bwd IAT Mean": "bwd_iat_mean",
    "SYN Flag Count": "syn_flag_count",
    "PSH Flag Count": "psh_flag_count",
    "ACK Flag Count": "ack_flag_count",
    "Down/Up Ratio": "down_up_ratio",
    "Average Packet Size": "pkt_size_avg",
}


def normalize_label(raw: object) -> str:
    """Canonicalize a raw dataset label.

    CICIDS2017 labels carry stray whitespace, inconsistent casing, and a
    non-ASCII dash in the Web-Attack labels that different mirrors store as a
    cp1252 byte (0x96) or a UTF-8 replacement char (U+FFFD): e.g.
    ``"Web Attack \x96 Brute Force"``. We fold any of those to ``-``, collapse
    whitespace, and upper-case BENIGN so the benign class is a single value;
    attack labels are otherwise left intact.
    """
    s = str(raw)
    for junk in ("\x96", "\x97", "�"):
        s = s.replace(junk, "-")
    s = " ".join(s.split())
    return BENIGN_LABEL if s.upper() == BENIGN_LABEL else s


def validate_frame(df: pd.DataFrame, features: tuple[str, ...] = CANONICAL_FEATURES) -> None:
    """Raise ``ValueError`` unless *df* carries exactly the given feature set
    (default: the full canonical schema) plus the metadata columns."""
    expected = set(features) | set(META_COLUMNS)
    missing = expected - set(df.columns)
    extra = set(df.columns) - expected
    if missing or extra:
        raise ValueError(f"schema mismatch: missing={sorted(missing)} extra={sorted(extra)}")
    if list(df.columns[: len(features)]) != list(features):
        raise ValueError("feature columns must lead the frame in canonical order")


# --------------------------------------------------------------------------- #
# per-dataset feature subsets                                                 #
# --------------------------------------------------------------------------- #
# A dataset with no real analogue for some canonical feature runs on a subset
# rather than a fabricated constant column (a zero column would still change
# the per-feature-RMS distance metric by diluting it). Every subset keeps
# canonical order and begins with COST_FEATURES, so the attacker-cost columns
# (dloop.adversary.base) sit at the same positions for every dataset.
COST_FEATURES: tuple[str, ...] = ("flow_duration", "fwd_packets", "bwd_packets",
                                  "fwd_bytes", "bwd_bytes")
assert CANONICAL_FEATURES[: len(COST_FEATURES)] == COST_FEATURES


def check_feature_subset(features: tuple[str, ...]) -> tuple[str, ...]:
    """Validate a per-dataset feature set: canonical names in canonical order,
    starting with :data:`COST_FEATURES`, optionally followed by extension
    features in :data:`EXTENSION_FEATURES` order. Returns it unchanged."""
    features = tuple(features)
    known = CANONICAL_FEATURES + EXTENSION_FEATURES
    unknown = [f for f in features if f not in known]
    if unknown:
        raise ValueError(f"not canonical or extension features: {unknown}")
    if list(features) != [f for f in known if f in features]:
        raise ValueError("feature subset must keep canonical order (extension features last)")
    if features[: len(COST_FEATURES)] != COST_FEATURES:
        raise ValueError(f"feature subset must start with {COST_FEATURES}")
    return features


# Reprocessed CICIDS2017 (Engelen et al., CNS2022 "improved" release; Phase A item B).
# Same CICFlowMeter-derived feature set as the original release, but four count
# columns were renamed (singular "Packet", lower-case "packets"). Every canonical
# feature has a direct analogue, so none is dropped. Mapping fixed in
# docs/phaseA/datasets-results.md before any number was computed from it.
CICIDS_FIXED_COLUMN_MAP: dict[str, str] = {
    **{raw: canon for raw, canon in CICIDS_COLUMN_MAP.items()
       if raw not in ("Total Fwd Packets", "Total Backward Packets",
                      "Total Length of Fwd Packets", "Total Length of Bwd Packets")},
    "Total Fwd Packet": "fwd_packets",
    "Total Bwd packets": "bwd_packets",
    "Total Length of Fwd Packet": "fwd_bytes",
    "Total Length of Bwd Packet": "bwd_bytes",
}
CICIDS_FIXED_LABEL_COLUMN = "Label"
CICIDS_FIXED_TIMESTAMP_COLUMN = "Timestamp"
# Engelen et al. tag flows that belong to an attack but carried no malicious
# payload (e.g. a failed login, a TCP handshake with no request) as "<family> - Attempted".
CICIDS_FIXED_ATTEMPTED_SUFFIX = " - Attempted"


# UNSW-NB15 (Argus/Bro features; Phase A item B). Its part CSVs are headerless;
# column names come from the official dictionary NUSW-NB15_features.csv, matched
# ignoring case and whitespace (the dictionary spells e.g. "Sload", "ct_src_ ltm").
# Only canonical features with a direct per-flow analogue are mapped; the other 15
# are left out of this dataset's run rather than fabricated or derived (see
# docs/phaseA/datasets-results.md §2). Keys are normalized dictionary names;
# values are (canonical feature, multiplier into CICFlowMeter units).
UNSW_COLUMN_MAP: dict[str, tuple[str, float]] = {
    "dur": ("flow_duration", 1e6),        # seconds -> microseconds
    "spkts": ("fwd_packets", 1.0),
    "dpkts": ("bwd_packets", 1.0),
    "sbytes": ("fwd_bytes", 1.0),
    "dbytes": ("bwd_bytes", 1.0),
    "smeansz": ("fwd_pkt_len_mean", 1.0),
    "dmeansz": ("bwd_pkt_len_mean", 1.0),
    "sintpkt": ("fwd_iat_mean", 1e3),     # milliseconds -> microseconds
    "dintpkt": ("bwd_iat_mean", 1e3),     # milliseconds -> microseconds
}
UNSW_FEATURES: tuple[str, ...] = tuple(
    f for f in CANONICAL_FEATURES if f in {c for c, _ in UNSW_COLUMN_MAP.values()}
)
UNSW_LABEL_COLUMN = "label"          # 0 normal / 1 attack
UNSW_CATEGORY_COLUMN = "attack_cat"  # attack family; blank for normal rows
UNSW_TIMESTAMP_COLUMN = "stime"      # record start time, unix seconds
# The release spells one family two ways.
UNSW_CATEGORY_ALIASES: dict[str, str] = {"Backdoors": "Backdoor"}


# UQ NetFlow v2 datasets (Sarhan, Layeghy, Portmann 2022; Phase R item R3,
# DECISIONS.md §31). One mapping for all three. Rule, fixed before any file was
# opened: keep every field that is a non-negative magnitude; drop endpoint
# identifiers (IPV4_SRC_ADDR, IPV4_DST_ADDR, L4_SRC_PORT, L4_DST_PORT) and
# categorical codes / bitmasks (PROTOCOL, L7_PROTO, TCP_FLAGS, CLIENT_TCP_FLAGS,
# SERVER_TCP_FLAGS, ICMP_TYPE, ICMP_IPV4_TYPE, DNS_QUERY_ID, DNS_QUERY_TYPE,
# FTP_COMMAND_RET_CODE), whose numeric distance is meaningless under the
# per-feature-RMS metric. The five fields with a direct CICFlowMeter analogue map
# onto COST_FEATURES (IN = src->dst = forward); the rest are extension features.
# Values: (feature, multiplier into CICFlowMeter units).
NETFLOW_V2_COLUMN_MAP: dict[str, tuple[str, float]] = {
    "FLOW_DURATION_MILLISECONDS": ("flow_duration", 1e3),   # ms -> microseconds
    "IN_PKTS": ("fwd_packets", 1.0),
    "OUT_PKTS": ("bwd_packets", 1.0),
    "IN_BYTES": ("fwd_bytes", 1.0),
    "OUT_BYTES": ("bwd_bytes", 1.0),
    **{f[3:].upper(): (f, 1.0) for f in NETFLOW_V2_EXTENSION_FEATURES},
}
NETFLOW_V2_FEATURES: tuple[str, ...] = COST_FEATURES + NETFLOW_V2_EXTENSION_FEATURES
NETFLOW_V2_DROPPED: tuple[str, ...] = (
    "IPV4_SRC_ADDR", "L4_SRC_PORT", "IPV4_DST_ADDR", "L4_DST_PORT", "PROTOCOL", "L7_PROTO",
    "TCP_FLAGS", "CLIENT_TCP_FLAGS", "SERVER_TCP_FLAGS", "ICMP_TYPE", "ICMP_IPV4_TYPE",
    "DNS_QUERY_ID", "DNS_QUERY_TYPE", "FTP_COMMAND_RET_CODE",
)
NETFLOW_V2_LABEL_COLUMN = "Label"     # 0 benign / 1 attack
NETFLOW_V2_ATTACK_COLUMN = "Attack"   # family; "Benign" for benign rows


def normalize_column_name(name: object) -> str:
    """Dictionary/header name -> match key: lower-case, all whitespace removed."""
    return "".join(str(name).split()).lower()
