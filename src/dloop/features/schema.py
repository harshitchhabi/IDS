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

# The two columns CICIDS2017 is documented to fill with NaN / +-Inf: they are
# byte/packet counts divided by a flow duration that can be zero.
RATE_FEATURES: frozenset[str] = frozenset({"flow_bytes_per_s", "flow_pkts_per_s"})

# Every canonical feature is a physically non-negative quantity (a duration, a
# count, a length, an inter-arrival time, a ratio). A negative value is a known
# CICIDS2017 artifact (e.g. negative "Flow Duration") and marks a corrupt row.
NONNEGATIVE_FEATURES: frozenset[str] = frozenset(CANONICAL_FEATURES)

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

    CICIDS2017 labels carry stray whitespace and inconsistent casing
    (``"BENIGN"`` vs ``"Web Attack \x96 Brute Force"``). We upper-case BENIGN so
    the benign class is a single value and leave attack labels otherwise intact.
    """
    s = str(raw).strip()
    return BENIGN_LABEL if s.upper() == BENIGN_LABEL else s


def validate_frame(df: pd.DataFrame) -> None:
    """Raise ``ValueError`` unless *df* carries exactly the canonical schema."""
    expected = set(CANONICAL_FEATURES) | set(META_COLUMNS)
    missing = expected - set(df.columns)
    extra = set(df.columns) - expected
    if missing or extra:
        raise ValueError(f"schema mismatch: missing={sorted(missing)} extra={sorted(extra)}")
    if list(df.columns[: len(CANONICAL_FEATURES)]) != list(CANONICAL_FEATURES):
        raise ValueError("feature columns must lead the frame in canonical order")
