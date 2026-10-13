"""Unit tests for src/petro_decline/wells.py."""

from __future__ import annotations

import pandas as pd

from petro_decline.wells import well_profile

MONTHS = pd.date_range("2022-01-01", "2023-12-01", freq="MS")  # 24 months


def _rows(well_id: str, volumes: dict) -> list[dict]:
    """OIL rows for one well; `volumes` maps a month to its volume."""
    return [
        {
            "ProductionMonth": month,
            "ReportingFacilityID": "FAC",
            "FromToID": well_id,
            "ProductID": "OIL",
            "Volume": volume,
            "IsInjector": False,
        }
        for month, volume in volumes.items()
    ]


def _well_level() -> pd.DataFrame:
    rows = []
    # steady CSS well that shuts in for steaming twice
    css = {m: (0.0 if i in (8, 17) else 400.0 - 10 * (i % 9)) for i, m in enumerate(MONTHS)}
    rows += _rows("CSS_WELL_W400", css)
    # starts in month 8, runs 4,000/month with no shut-in: SAGD-like
    rows += _rows("SAGD_WELL_W400", {m: 4000.0 for m in MONTHS[8:]})
    # first appears in the last three months
    rows += _rows("TOO_NEW_W400", {m: 300.0 for m in MONTHS[-3:]})
    # never above the minimum volume
    rows += _rows("TINY_WELL_W400", {m: 20.0 for m in MONTHS})
    # sidetrack: event suffix 02
    rows += _rows("SIDETRACK_W402", {m: 250.0 for m in MONTHS})
    return pd.DataFrame(rows)


def _profile() -> pd.DataFrame:
    return well_profile(_well_level()).set_index("FromToID")


def test_css_well_is_kept():
    row = _profile().loc["CSS_WELL_W400"]
    assert row["process"] == "css"
    assert row["excluded_reason"] == ""
    assert row["shut_in_months"] == 2
    assert not row["new_in_window"]


def test_sustained_high_rate_with_no_shut_in_is_continuous():
    row = _profile().loc["SAGD_WELL_W400"]
    assert row["process"] == "continuous"
    assert row["excluded_reason"] == "continuous process"
    assert row["new_in_window"]


def test_short_history_is_excluded():
    assert _profile().loc["TOO_NEW_W400", "excluded_reason"] == "under 6 months of history"


def test_tiny_well_is_excluded_for_volume():
    assert _profile().loc["TINY_WELL_W400", "excluded_reason"] == "below minimum volume"


def test_event_suffix_marks_a_redrill():
    profile = _profile()
    assert profile.loc["SIDETRACK_W402", "is_redrill"]
    assert not profile.loc["CSS_WELL_W400", "is_redrill"]


def test_wells_reporting_from_the_first_month_are_not_new():
    profile = _profile()
    assert not profile.loc["SIDETRACK_W402", "new_in_window"]
