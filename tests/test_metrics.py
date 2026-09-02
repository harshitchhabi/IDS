"""Metric correctness on hand-computed toy cases."""

import numpy as np
import pytest

from dloop.models.metrics import auroc, binary_metrics, confusion_counts


def test_confusion_counts_hand_case():
    y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    p = np.array([0, 0, 1, 0, 1, 1, 0, 1])  # 1 FP, 1 FN
    tn, fp, fn, tp = confusion_counts(y, p)
    assert (tn, fp, fn, tp) == (3, 1, 1, 3)


def test_binary_metrics_hand_case():
    y = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    score = np.array([0.1, 0.2, 0.3, 0.9, 0.4, 0.8, 0.7, 0.2, 0.95, 0.6])
    m = binary_metrics(y, score, threshold=0.5)
    # benign >= 0.5: just the 0.9  -> FP=1, TN=4  -> FPR = 1/5
    # attack >= 0.5: 0.8,0.7,0.95,0.6 -> TP=4, FN=1 -> TPR = 4/5
    assert m["fp"] == 1 and m["tn"] == 4 and m["tp"] == 4 and m["fn"] == 1
    assert m["fpr"] == pytest.approx(0.2)
    assert m["tpr"] == pytest.approx(0.8)
    assert m["precision"] == pytest.approx(4 / 5)
    assert m["f1"] == pytest.approx(2 * 0.8 * 0.8 / (0.8 + 0.8))


def test_auroc_perfect_and_random():
    y = np.array([0, 0, 0, 1, 1, 1])
    assert auroc(y, np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])) == pytest.approx(1.0)
    assert auroc(y, np.array([0.6, 0.5, 0.4, 0.3, 0.2, 0.1])) == pytest.approx(0.0)
    # tie -> 0.5
    assert auroc(np.array([0, 1]), np.array([0.5, 0.5])) == pytest.approx(0.5)


def test_auroc_known_value():
    # 2 pos, 2 neg; pos ranks {2,4} of scores [n,n,p,p] sorted -> AUROC = 0.75
    y = np.array([0, 0, 1, 1])
    s = np.array([0.1, 0.3, 0.2, 0.4])
    assert auroc(y, s) == pytest.approx(0.75)


def test_auroc_nan_when_one_class_absent():
    assert np.isnan(auroc(np.array([0, 0, 0]), np.array([0.1, 0.2, 0.3])))
