"""Unit tests for src/petro_decline/decline.py: Arps fitting and model selection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from petro_decline.decline import ArpsModel, fit_all_cycles, fit_cycle, predict


def test_exponential_fit_recovers_known_parameters():
    """Fitting synthetic exponential data should recover qi/Di close to the values
    used to generate it, and pick the exponential model (it's the true model here,
    so it should win on AICc even though hyperbolic is also tried).
    """
    qi_true, di_true = 500.0, 0.15
    t = np.arange(10, dtype=float)
    q = qi_true * np.exp(-di_true * t)

    result = fit_cycle(t, q, short_cycle=False)

    assert result["model"] == "exponential"
    assert result["qi"] == pytest.approx(qi_true, rel=0.05)
    assert result["Di"] == pytest.approx(di_true, rel=0.05)
    assert result["r_squared"] > 0.99


def test_hyperbolic_fit():
    """Same idea, but for a genuinely hyperbolic curve (b != 0, 1) — the fit
    should recover b close to the true value, not collapse to exponential/harmonic.
    """
    qi_true, di_true, b_true = 800.0, 0.25, 0.6
    t = np.arange(12, dtype=float)
    q = qi_true / (1 + b_true * di_true * t) ** (1 / b_true)

    result = fit_cycle(t, q, short_cycle=False)

    assert result["model"] == "hyperbolic"
    assert result["qi"] == pytest.approx(qi_true, rel=0.05)
    assert result["b"] == pytest.approx(b_true, abs=0.1)


def test_harmonic_fit_recovers_known_parameters():
    qi_true, di_true = 300.0, 0.10
    t = np.arange(10, dtype=float)
    q = qi_true / (1 + di_true * t)

    result = fit_cycle(t, q, short_cycle=False)

    assert result["model"] == "harmonic"
    assert result["b"] == pytest.approx(1.0)
    assert result["qi"] == pytest.approx(qi_true, rel=0.05)
    assert result["Di"] == pytest.approx(di_true, rel=0.05)


def test_too_few_points_returns_no_model():
    """n=3 can't support even the simplest model (k=2 needs n>=4) — should refuse
    to fit rather than let a 3-parameter hyperbolic pass through all 3 points.
    This is the exact bug this project's AICc fix addressed.
    """
    t = np.array([0.0, 1.0, 2.0])
    q = np.array([500.0, 400.0, 320.0])

    result = fit_cycle(t, q, short_cycle=True)

    assert result["model"] is None
    assert result["low_confidence"] is True
    assert "too few" in result["low_confidence_reason"]


def test_short_cycle_flag_propagates_to_low_confidence():
    qi_true, di_true = 500.0, 0.2
    t = np.arange(5, dtype=float)  # enough points to fit (n=5 >= 4), but flagged short
    q = qi_true * np.exp(-di_true * t)

    result = fit_cycle(t, q, short_cycle=True)

    assert result["model"] is not None
    assert result["low_confidence"] is True
    assert "short cycle" in result["low_confidence_reason"]


def test_predict_reproduces_fitted_curve():
    """predict() should closely reproduce the data a fit was built from — a basic
    sanity check that plotting uses the same math the fit itself used.
    """
    qi_true, di_true = 400.0, 0.18
    t = np.arange(8, dtype=float)
    q = qi_true * np.exp(-di_true * t)

    result = fit_cycle(t, q, short_cycle=False)
    predicted = predict(t, result["model"], result["qi"], result["Di"], result["b"])

    assert predicted == pytest.approx(q, rel=0.05)


def test_fit_all_cycles_excludes_zero_fill_shut_in_months():
    """A month with zero volume (data.well_oil_series's fill value for a Petrinex
    gap, i.e. a shut-in/soak month) should be dropped before fitting, not treated
    as a real observation — this is the exact bug the zero-fill fix addressed.

    Verified by checking that fit_all_cycles's result on a series with a zero-run
    matches fit_cycle called directly on the same points with the zero-run
    removed by hand — i.e. the true elapsed month index (0,1,2,3,6,7,8,9, skipping
    the shut-in months 4-5) is what should reach curve_fit, not a renumbered,
    contiguous 0..7.
    """
    qi_true, di_true = 600.0, 0.2
    months = pd.date_range("2023-01-01", periods=10, freq="MS")
    clean_values = qi_true * np.exp(-di_true * np.arange(10))

    # Same decline, but months 4-5 (a workover) are reported as zero.
    with_shut_in = clean_values.copy()
    with_shut_in[4:6] = 0.0
    series_with_shut_in = pd.Series(with_shut_in, index=months)

    cycles_df = pd.DataFrame(
        {
            "Battery": ["TestBattery"],
            "FromToID": ["WELL1"],
            "start": [months[0]],
            "end": [months[-1]],
            "duration_months": [10],
            "short_cycle": [False],
            "is_startup_ramp": [False],
        }
    )

    fits_with_shut_in = fit_all_cycles(cycles_df, {"TestBattery": {"WELL1": series_with_shut_in}})

    # What the fit *should* see: true elapsed months, shut-in points dropped
    # entirely rather than renumbered.
    expected_t = np.array([0.0, 1.0, 2.0, 3.0, 6.0, 7.0, 8.0, 9.0])
    expected_q = np.delete(clean_values, [4, 5])
    expected_fit = fit_cycle(expected_t, expected_q, short_cycle=False)

    assert fits_with_shut_in.loc[0, "qi"] == pytest.approx(expected_fit["qi"], rel=1e-6)
    assert fits_with_shut_in.loc[0, "Di"] == pytest.approx(expected_fit["Di"], rel=1e-6)
    # And, as a sanity check, that this recovers the true generating parameters,
    # not just "matches the hand-built expectation" circularly.
    assert fits_with_shut_in.loc[0, "qi"] == pytest.approx(qi_true, rel=0.05)
    assert fits_with_shut_in.loc[0, "Di"] == pytest.approx(di_true, rel=0.05)


def test_arps_model_enum_values_match_config_strings():
    """predict() takes model as a plain string (from a CSV column) — confirm the
    enum's values round-trip through that string interface.
    """
    for model in ArpsModel:
        assert ArpsModel(model.value) is model
