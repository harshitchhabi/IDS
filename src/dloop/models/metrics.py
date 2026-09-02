"""Binary detection metrics — FPR and TPR first, never bare accuracy.

CLAUDE.md metrics discipline: "Report FPR and TPR, never bare accuracy — the
classes are wildly imbalanced and accuracy will look great while the system is
useless." Every function here is small enough to hand-check, and the tests do.
"""

from __future__ import annotations

import numpy as np


def confusion_counts(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[int, int, int, int]:
    """Return ``(tn, fp, fn, tp)`` for 0/1 arrays."""
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    return tn, fp, fn, tp


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b else 0.0


def auroc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Rank-based AUROC (Mann-Whitney). ``nan`` if only one class is present."""
    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score, dtype="float64")
    n_pos = int(np.sum(y_true == 1))
    n_neg = int(np.sum(y_true == 0))
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    # tie-corrected ranks (1-based), then the Mann-Whitney identity
    _, inv, counts = np.unique(y_score, return_inverse=True, return_counts=True)
    csum = np.cumsum(counts)
    avg_rank = (csum - counts + csum + 1) / 2.0
    ranks = avg_rank[inv]
    r_pos = ranks[y_true == 1].sum()
    return float((r_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def binary_metrics(y_true: np.ndarray, y_score: np.ndarray, threshold: float) -> dict:
    """Full metric bundle at *threshold* (predict attack when score >= threshold)."""
    y_true = np.asarray(y_true).astype(int)
    y_score = np.asarray(y_score, dtype="float64")
    y_pred = (y_score >= threshold).astype(int)
    tn, fp, fn, tp = confusion_counts(y_true, y_pred)

    fpr = _safe_div(fp, fp + tn)
    tpr = _safe_div(tp, tp + fn)          # == recall
    precision = _safe_div(tp, tp + fp)
    f1 = _safe_div(2 * precision * tpr, precision + tpr)
    return {
        "threshold": float(threshold),
        "fpr": fpr,
        "tpr": tpr,
        "precision": precision,
        "f1": f1,
        "auroc": auroc(y_true, y_score),
        "tn": tn, "fp": fp, "fn": fn, "tp": tp,
        "n": int(len(y_true)),
        "n_benign": int(np.sum(y_true == 0)),
        "n_attack": int(np.sum(y_true == 1)),
    }
