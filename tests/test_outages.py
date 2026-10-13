"""Unit tests for src/petro_decline/outages.py."""

from __future__ import annotations

import numpy as np
import pandas as pd

from petro_decline.outages import fill_outages, find_outage_months, mask_outages


def _battery(factors: dict | None = None) -> pd.DataFrame:
    """20 wells producing 31 m3 every month, scaled by `factors` for chosen months."""
    months = pd.date_range("2023-01-01", "2024-06-01", freq="MS")
    rows = []
    for month in months:
        scale = (factors or {}).get(month.strftime("%Y-%m"), 1.0)
        for well in range(20):
            rows.append(
                {"ProductionMonth": month, "FromToID": f"W{well}", "ProductID": "OIL", "Volume": 31.0 * scale}
            )
    return pd.DataFrame(rows)


def test_a_steady_battery_has_no_outages():
    assert len(find_outage_months(_battery())) == 0


def test_a_sharp_battery_wide_dip_is_flagged():
    outages = find_outage_months(_battery({"2023-08": 0.3, "2023-09": 0.1}))

    assert [d.strftime("%Y-%m") for d in outages] == ["2023-08", "2023-09"]


def test_a_mild_dip_is_left_alone():
    assert len(find_outage_months(_battery({"2023-08": 0.9}))) == 0


def test_mask_sets_outage_months_to_nan():
    series = pd.Series([10.0, 10.0, 2.0, 10.0], index=pd.date_range("2023-01-01", periods=4, freq="MS"))
    masked = mask_outages(series, pd.DatetimeIndex(["2023-03-01"]))

    assert np.isnan(masked["2023-03-01"])
    assert masked["2023-02-01"] == 10.0


def test_fill_interpolates_across_the_outage():
    series = pd.Series([10.0, 10.0, 2.0, 2.0, 10.0], index=pd.date_range("2023-01-01", periods=5, freq="MS"))
    filled = fill_outages(series, pd.DatetimeIndex(["2023-03-01", "2023-04-01"]))

    assert list(filled.round(1)) == [10.0, 10.0, 10.0, 10.0, 10.0]
