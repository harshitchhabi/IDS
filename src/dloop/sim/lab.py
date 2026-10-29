"""Phase B lab-dataset builder (DECISIONS.md §32.0).

Turns the lab's captured-labelled-extracted flows into the paper's four
partitions. Unlike the CSV datasets, the partition of a lab flow is decided by
its **role** (what generator produced it and where it went), not by feature-space
routing:

* benign flows (prod-bound, from the dense benign capture) -> split into
  ``seed_train`` benign, ``prod_benign`` and ``trusted_eval`` benign;
* real attack flows (attacker -> prod/honeypot) -> ``seed_train`` and
  ``trusted_eval`` attack rows (genuine malicious traffic);
* honeypot-bound **mimic** flows of the primary strategy -> ``honeypot_pool``,
  with ``BINARY_LABEL = 0`` (they are truly benign; the A1 poison is these rows
  labelled malicious by the honeypot policy).

Leakage guards, same as the paper but applied with its own semantics:

* **exact-duplicate removal** (hygiene: no identical flow in two partitions);
* the **guard (c) NN leakage check**, reported, and gated on the *attack* class
  only -- benign near-proximity across partitions is the normal state of real
  traffic (``dloop.sim.partition``), and for A1 the mimic flows are *meant* to sit
  near benign, so that proximity is the phenomenon under study, not a leak.

``assert_disjoint`` (exact float32 row identity) between ``trusted_eval`` and the
training partitions is asserted before the data is returned.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dloop.features import schema
from dloop.features.normalize import fit_normalizer
from dloop.logging_config import get_logger
from dloop.sim.partition import (
    LeakageReport, PartitionConfig, PartitionedData, _nn_leakage_check, _row_hashes,
)

log = get_logger("sim.lab")

# ground-truth `kind` values, by role
MIMIC_KINDS = {"mimic_profile": "profile", "mimic_oracle": "oracle", "mimic_replay": "replay"}
ATTACK_KINDS = {"portscan": "PortScan", "ssh_bruteforce": "SSH-Bruteforce",
                "web_probe": "WebProbe"}


@dataclass
class LabSplitConfig:
    seed_benign_frac: float = 0.34
    prod_benign_frac: float = 0.33
    eval_benign_frac: float = 0.33
    eval_attack_frac: float = 0.40      # share of real attacks held out for eval
    primary_strategy: str = "oracle"    # which mimic strategy feeds honeypot_pool
    seed: int = 20260903


def _clean(df: pd.DataFrame, feats: tuple[str, ...]) -> pd.DataFrame:
    """Minimal cleaning that preserves the role columns: numeric coercion,
    +-Inf -> NaN, drop any-NaN / negative rows, drop exact feature duplicates."""
    df = df.copy()
    for f in feats:
        df[f] = pd.to_numeric(df[f], errors="coerce")
    df[list(feats)] = df[list(feats)].replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=list(feats))
    df = df[(df[list(feats)] >= 0).all(axis=1)]
    df = df.drop_duplicates(subset=list(feats) + ["_role", "_fam"]).reset_index(drop=True)
    return df


def build_lab_partitions(labelled: pd.DataFrame, cfg: LabSplitConfig | None = None,
                         features: tuple[str, ...] = schema.CANONICAL_FEATURES) -> PartitionedData:
    cfg = cfg or LabSplitConfig()
    feats = schema.check_feature_subset(tuple(features))
    rng = np.random.default_rng(cfg.seed)

    df = labelled.copy()
    # role from true_intent; family/strategy from true_kind
    kind = df.get("true_kind", pd.Series([""] * len(df))).astype(str)
    role = np.where(df["true_intent"].to_numpy() == "benign", "benign",
                    np.where(df["true_intent"].to_numpy() == "attack", "attack",
                             np.where(df["true_intent"].to_numpy() == "poison", "mimic", "drop")))
    df["_role"] = role
    df["_fam"] = [ATTACK_KINDS.get(k, "Attack") if r == "attack"
                  else MIMIC_KINDS.get(k, "mimic") if r == "mimic" else schema.BENIGN_LABEL
                  for r, k in zip(role, kind)]
    df = df[df["_role"] != "drop"]
    df = _clean(df, feats)

    benign = df[df["_role"] == "benign"]
    attack = df[df["_role"] == "attack"]
    mimic = df[(df["_role"] == "mimic") & (df["_fam"] == cfg.primary_strategy)]
    if benign.empty or mimic.empty:
        raise ValueError(f"lab build needs benign and '{cfg.primary_strategy}' mimic flows; "
                         f"have benign={len(benign)} mimic={len(mimic)}")

    # --- benign three-way split (seed / prod / eval) ---
    bidx = rng.permutation(len(benign))
    n = len(benign)
    n_seed = int(cfg.seed_benign_frac * n)
    n_prod = int(cfg.prod_benign_frac * n)
    seed_b = benign.iloc[np.sort(bidx[:n_seed])]
    prod_b = benign.iloc[np.sort(bidx[n_seed:n_seed + n_prod])]
    eval_b = benign.iloc[np.sort(bidx[n_seed + n_prod:])]

    # --- real attacks: seed vs eval ---
    aidx = rng.permutation(len(attack))
    n_eval_a = int(cfg.eval_attack_frac * len(attack))
    eval_a = attack.iloc[np.sort(aidx[:n_eval_a])]
    seed_a = attack.iloc[np.sort(aidx[n_eval_a:])]

    def _frame(parts: list[pd.DataFrame]) -> pd.DataFrame:
        f = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=df.columns)
        f = f.copy()
        f[schema.LABEL] = f["_fam"].where(f["_role"] == "attack", schema.BENIGN_LABEL)
        f[schema.BINARY_LABEL] = (f["_role"] == "attack").astype("int64")
        f[schema.DAY] = "lab"
        return f.reset_index(drop=True)

    frames = {
        "seed_train": _frame([seed_b, seed_a]),
        "prod_benign": _frame([prod_b]),
        "honeypot_pool": _frame([mimic]),      # BINARY_LABEL 0 (true benign) -> pool_benign
        "trusted_eval": _frame([eval_b, eval_a]),
    }

    normalizer = fit_normalizer(pd.concat(frames.values(), ignore_index=True), feats)
    report = LeakageReport(strategy="lab_role")

    # guard (c): NN leakage check (reported; gated on attack class only)
    _nn_leakage_check(frames, normalizer, PartitionConfig(), report)

    # assert exact-row disjointness: trusted_eval vs each training partition
    te_keys = set(_row_hashes(frames["trusted_eval"], feats).tolist())
    for p in ("seed_train", "prod_benign", "honeypot_pool"):
        overlap = te_keys & set(_row_hashes(frames[p], feats).tolist())
        if overlap:
            raise AssertionError(f"{len(overlap)} identical rows shared by trusted_eval and {p}")

    log.info("lab partitions built", primary_strategy=cfg.primary_strategy,
             rows={p: len(f) for p, f in frames.items()},
             attack_families=sorted(set(attack["_fam"])), leak_warning=report.leak_warning)
    return PartitionedData(frames=frames, cleaning={}, leakage=report,
                           config=PartitionConfig(), normalizer=normalizer, features=feats)
