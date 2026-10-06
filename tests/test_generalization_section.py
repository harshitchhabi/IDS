"""The generalization section's table and prose must not silently drift from the Phase A CSVs
they were written from.

Same pattern as test_paper_figures.py's F5-caption checks: a LaTeX table is a string an editor
can hand-edit without re-running anything, so nothing else enforces that it still matches the
underlying data. This reads the key numbers straight from results/phaseA/ and checks the paper
text states the same ones.
"""

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

SECTION_FILE = Path("paper/sections/07a_generalization.tex")
CICIDS_FIXED_STATS = Path("results/phaseA/datasets/cicids-fixed/stats.csv")
UNSW_STATS = Path("results/phaseA/datasets/unsw-nb15/stats.csv")
CICIDS_FIXED_DEGEN = Path("results/phaseA/datasets/cicids-fixed/nn_degeneracy_by_grid.csv")
UNSW_DEGEN = Path("results/phaseA/datasets/unsw-nb15/nn_degeneracy_by_grid.csv")
MODELS_STATS = Path("results/phaseA/models/stats.csv")


def _skip_if_no_data():
    for p in (CICIDS_FIXED_STATS, UNSW_STATS, CICIDS_FIXED_DEGEN, UNSW_DEGEN, MODELS_STATS):
        if not p.exists():
            pytest.skip(f"{p} not present")


def _b1_dfpr(path: Path, model: str, ratio: float) -> float:
    df = pd.read_csv(path)
    row = df[(df.metric == "dFPR") & (df.threshold_mode == "fixed")
             & (df.jitter == 0.0) & (df.model == model) & (df.ratio == ratio)]
    assert len(row) == 1, f"expected exactly one row for {model} r={ratio} in {path}"
    return float(row["mean"].iloc[0])


def _benign_median_nn(path: Path) -> float:
    df = pd.read_csv(path)
    row = df[(df["class"] == "benign") & (df["grid"] == 0.005)]
    assert len(row) == 1, f"expected exactly one benign/grid-0.005 row in {path}"
    return float(row["median_rms"].iloc[0])


def test_degeneracy_table_matches_csvs():
    _skip_if_no_data()
    section = SECTION_FILE.read_text(encoding="utf-8")
    cf_benign = _benign_median_nn(CICIDS_FIXED_DEGEN)
    unsw_benign = _benign_median_nn(UNSW_DEGEN)
    assert cf_benign == pytest.approx(0.0107, abs=0.0001)
    assert unsw_benign == pytest.approx(0.0037, abs=0.0001)
    # the table/prose state these to 4 dp; check the stated strings are actually present,
    # not just that the CSV happens to still round the same way
    assert "0.0107" in section
    assert "0.0037" in section


def test_b1_copy_fidelity_numbers_match_csvs():
    _skip_if_no_data()
    section = SECTION_FILE.read_text(encoding="utf-8")
    cf_rf_02 = _b1_dfpr(CICIDS_FIXED_STATS, "rf", 0.2)
    cf_rf_05 = _b1_dfpr(CICIDS_FIXED_STATS, "rf", 0.5)
    cf_xgb_02 = _b1_dfpr(CICIDS_FIXED_STATS, "xgboost", 0.2)
    cf_xgb_05 = _b1_dfpr(CICIDS_FIXED_STATS, "xgboost", 0.5)
    unsw_rf_02 = _b1_dfpr(UNSW_STATS, "rf", 0.2)
    unsw_rf_05 = _b1_dfpr(UNSW_STATS, "rf", 0.5)
    unsw_xgb_02 = _b1_dfpr(UNSW_STATS, "xgboost", 0.2)
    unsw_xgb_05 = _b1_dfpr(UNSW_STATS, "xgboost", 0.5)

    # reprocessed CICIDS2017: paper states ratio 0.2 and 0.5 RF/XGBoost, 3dp
    assert cf_rf_02 == pytest.approx(0.985, abs=0.001)
    assert cf_rf_05 == pytest.approx(0.989, abs=0.001)
    assert cf_xgb_02 == pytest.approx(0.986, abs=0.001)
    assert cf_xgb_05 == pytest.approx(0.986, abs=0.001)
    # UNSW-NB15
    assert unsw_rf_02 == pytest.approx(0.092, abs=0.001)
    assert unsw_rf_05 == pytest.approx(0.254, abs=0.001)
    assert unsw_xgb_02 == pytest.approx(0.016, abs=0.001)
    assert unsw_xgb_05 == pytest.approx(0.211, abs=0.001)

    for needle in ("0.985", "0.989", "0.986", "0.092", "0.254", "0.016", "0.211"):
        assert needle in section, f"{needle!r} (from the Phase A CSVs) not found in {SECTION_FILE}"


def test_mlp_ratio_0_5_damage_matches_csv():
    _skip_if_no_data()
    df = pd.read_csv(MODELS_STATS)
    # df.mode is DataFrame.mode() (a method), not the "mode" column -- must index by name
    row = df[(df.model == "mlp") & (df.metric == "fpr") & (df["mode"] == "fixed")
             & (df.ratio == 0.5) & (df.jitter == 0.0)]
    assert len(row) == 1
    mean = float(row["mean"].iloc[0])
    assert mean == pytest.approx(0.409, abs=0.001)
    section = SECTION_FILE.read_text(encoding="utf-8")
    assert "0.409" in section


def test_section_does_not_overclaim_label_conflict_generality():
    """The generalization section exists specifically to say the label-conflict isolation does
    NOT generalize -- guard against a future edit quietly reversing that."""
    section = SECTION_FILE.read_text(encoding="utf-8")
    assert "does not generalize" in section.lower() or "doesn't generalize" in section.lower() \
        or "does not replicate" in section.lower()
