"""UQ NetFlow v2 loader: NF-UNSW-NB15-v2, NF-CSE-CIC-IDS2018-v2, NF-ToN-IoT-v2
(Sarhan, Layeghy, Portmann 2022; Phase R item R3, DECISIONS.md §31).

All three share one 43-field NetFlow v2 schema, so one loader and one column
mapping (:data:`schema.NETFLOW_V2_COLUMN_MAP`, fixed before any file was opened)
serve all three. The features are the five cost features (with a direct
CICFlowMeter analogue) followed by 24 NetFlow-native magnitudes; identifiers and
categorical codes are dropped, never encoded.

NetFlow v2 carries no flow timestamp. As with CICIDS2017's MachineLearningCVE
release, the within-day temporal partition therefore runs on file order:
:mod:`dloop.features.cleaning` synthesizes a monotonic timestamp from row order.
The repository copy of each dataset is a stratified subsample that keeps file
order (``experiments/phaseR_netflow_subsample.py``), so that order is preserved.
Every row is tagged with one capture block, :data:`DAY`; the datasets have no
documented day split.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dloop.features import schema
from dloop.logging_config import get_logger

log = get_logger("sim.netflow_v2")

DEFAULT_ROOT = Path("data/netflow-v2")
# --dataset / --source value -> file stem (``<root>/<stem>.csv``)
DATASETS: dict[str, str] = {
    "nf-unsw-nb15-v2": "NF-UNSW-NB15-v2",
    "nf-cse-cic-ids2018-v2": "NF-CSE-CIC-IDS2018-v2",
    "nf-ton-iot-v2": "NF-ToN-IoT-v2",
}
DAY = "all"


def path_for(source: str, root: Path | str = DEFAULT_ROOT) -> Path:
    if source not in DATASETS:
        raise ValueError(f"unknown NetFlow v2 dataset {source!r}; expected one of {sorted(DATASETS)}")
    return Path(root) / f"{DATASETS[source]}.csv"


def files_for(source: str, root: Path | str = DEFAULT_ROOT) -> list[Path]:
    """The CSV(s) holding a dataset, in row order: ``<stem>.csv``, or, when the
    subsample was split by row range to fit a zip limit, ``<stem>.part01.csv``,
    ``<stem>.part02.csv``, ... (zero-padded, so name order is row order). Empty if absent."""
    whole = path_for(source, root)
    if whole.exists():
        return [whole]
    return sorted(Path(root).glob(f"{DATASETS[source]}.part[0-9][0-9].csv"))


def is_available(source: str, root: Path | str = DEFAULT_ROOT) -> bool:
    return bool(files_for(source, root))


def load_raw_by_day(source: str, root: Path | str = DEFAULT_ROOT) -> dict[str, pd.DataFrame]:
    """``{DAY: frame}`` with :data:`schema.NETFLOW_V2_FEATURES` and ``label``, in file order."""
    paths = files_for(source, root)
    if not paths:
        raise FileNotFoundError(f"{path_for(source, root)} (or its .partNN.csv pieces) missing "
                                "(see harshitchhabi/IDS-data netflow-v2/README.md)")
    needed = [*schema.NETFLOW_V2_COLUMN_MAP, schema.NETFLOW_V2_LABEL_COLUMN,
              schema.NETFLOW_V2_ATTACK_COLUMN]
    header = None
    for path in paths:
        h = [str(c).strip() for c in pd.read_csv(path, nrows=0).columns]
        if header is not None and h != header:
            raise ValueError(f"{path.name}'s header differs from {paths[0].name}'s; parts must share one header")
        header = h
        missing = [c for c in needed if c not in h]
        if missing:
            # the mapping is pre-registered; a mismatch is reported, never patched silently
            raise ValueError(f"{path.name} lacks pre-registered NetFlow v2 columns {missing}; header={h}")

    df = pd.concat([pd.read_csv(p, usecols=lambda c: str(c).strip() in needed, low_memory=False)
                    for p in paths], ignore_index=True)
    df.columns = [str(c).strip() for c in df.columns]
    out = pd.DataFrame(index=df.index)
    for raw, (feat, mult) in schema.NETFLOW_V2_COLUMN_MAP.items():
        out[feat] = pd.to_numeric(df[raw], errors="coerce") * mult
    out = out[list(schema.NETFLOW_V2_FEATURES)]

    fam = df[schema.NETFLOW_V2_ATTACK_COLUMN].astype(str).map(schema.normalize_label)
    is_attack = pd.to_numeric(df[schema.NETFLOW_V2_LABEL_COLUMN], errors="coerce")
    benign_fam = fam == schema.BENIGN_LABEL
    # binary label and family disagree, or no label: cannot label without guessing
    inconsistent = ((is_attack == 1) & benign_fam) | ((is_attack == 0) & ~benign_fam) | is_attack.isna()
    out[schema.LABEL] = fam
    out[schema.DAY] = DAY
    if inconsistent.any():
        log.info("dropping rows whose Label and Attack disagree", rows=int(inconsistent.sum()))
    out = out.loc[~inconsistent].reset_index(drop=True)
    log.info("NetFlow v2 load complete", source=source, rows=len(out),
             label_and_attack_disagree=int(inconsistent.sum()),
             families=out[schema.LABEL].value_counts().to_dict())
    return {DAY: out}
