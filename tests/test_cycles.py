"""Unit tests for src/petro_decline/cycles.py."""

from __future__ import annotations

import pandas as pd

from petro_decline.cycles import DetectionSettings, detect_cycles, passes_volume_filter


def _series(values) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2022-01-01", periods=len(values), freq="MS"), dtype=float)


# two re-steams: production drops to zero, then jumps back up
SAWTOOTH = [100, 80, 60, 45, 35, 25, 0, 120, 90, 65, 45, 30, 20, 0, 110, 80, 60, 40, 30, 20, 15, 10, 8, 6]


def test_detects_each_restart_peak():
    result = detect_cycles(_series(SAWTOOTH))

    starts = [d.strftime("%Y-%m") for d in result["cycle_starts"]]
    assert starts == ["2022-01", "2022-08", "2023-03"]


def test_first_cycle_is_startup_ramp_and_last_is_final():
    cycles = detect_cycles(_series(SAWTOOTH))["cycles"]

    assert [c["is_startup_ramp"] for c in cycles] == [True, False, False]
    assert [c["is_final_cycle"] for c in cycles] == [False, False, True]
    assert [c["duration_months"] for c in cycles] == [7, 7, 10]


def test_flat_zero_series_is_a_single_cycle():
    result = detect_cycles(_series([0.0] * 12))
    assert len(result["cycles"]) == 1


def test_peaks_closer_than_min_spacing_collapse_to_one():
    # 120 at month 7 and 118 at month 9, only 2 months apart; the taller one wins
    values = [100, 80, 60, 40, 30, 20, 0, 120, 60, 118, 70, 40, 30, 20, 10, 8]
    starts = detect_cycles(_series(values))["cycle_starts"]

    assert len(starts) == 2


def test_short_cycles_are_flagged():
    cycles = detect_cycles(_series(SAWTOOTH))["cycles"]
    assert not any(c["short_cycle"] for c in cycles)

    quick = [100, 60, 30, 0, 110, 60, 30, 0, 100, 60, 30, 20, 10, 8, 5, 3]
    flagged = detect_cycles(_series(quick))["cycles"]
    assert any(c["short_cycle"] for c in flagged)


def test_steam_gap_rule_rejects_a_hump_with_no_dip_before_it():
    # production sags to 20 and bumps to 45: prominent enough to count, but no near-zero month beforehand
    hump = [100, 80, 60, 40, 30, 20, 45, 40, 30, 25, 20, 15, 12, 10]

    assert len(detect_cycles(_series(hump))["cycle_starts"]) == 2
    strict = DetectionSettings(steam_gap_max_fraction=0.25)
    assert len(detect_cycles(_series(hump), strict)["cycle_starts"]) == 1


def test_steam_gap_rule_keeps_a_restart_after_a_zero_month():
    strict = DetectionSettings(steam_gap_max_fraction=0.25)
    starts = detect_cycles(_series(SAWTOOTH), strict)["cycle_starts"]

    assert len(starts) == 3


def test_volume_filter():
    assert passes_volume_filter(_series([10, 60, 20]))
    assert not passes_volume_filter(_series([10, 30, 20]))
