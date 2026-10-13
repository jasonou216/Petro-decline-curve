"""Plant-wide outages: months where a whole battery produced far less than usual.

A plant shutdown cuts every well at once, and the recovery afterwards looks
like a fresh peak in each well's series, so detection reads it as a wave of
re-steams. Months where the battery's total rate falls well below its own
local baseline are flagged here and masked out of detection and fitting.
"""

from __future__ import annotations

import pandas as pd

BASELINE_WINDOW_MONTHS = 13  # centered rolling median, six months either side
MIN_BASELINE_MONTHS = 5
DROP_THRESHOLD = 0.8  # flag months below this fraction of the baseline


def battery_monthly_rate(well_level: pd.DataFrame) -> pd.Series:
    """Battery oil rate in m3/day for each month."""
    oil = well_level[well_level["ProductID"] == "OIL"]
    monthly = oil.groupby("ProductionMonth")["Volume"].sum()
    return monthly / monthly.index.days_in_month


def find_outage_months(well_level: pd.DataFrame) -> pd.DatetimeIndex:
    """Months where the battery rate is under DROP_THRESHOLD of its rolling-median baseline."""
    rate = battery_monthly_rate(well_level)
    baseline = rate.rolling(BASELINE_WINDOW_MONTHS, center=True, min_periods=MIN_BASELINE_MONTHS).median()
    return rate.index[rate < DROP_THRESHOLD * baseline]


def mask_outages(series: pd.Series, outage_months: pd.DatetimeIndex) -> pd.Series:
    """The series with outage months set to NaN (dropped from curve fits, since NaN > 0 is False)."""
    return series.mask(series.index.isin(outage_months))


def fill_outages(series: pd.Series, outage_months: pd.DatetimeIndex) -> pd.Series:
    """The series with outage months linearly interpolated, for peak detection."""
    return mask_outages(series, outage_months).interpolate(limit_area="inside").ffill().bfill()
