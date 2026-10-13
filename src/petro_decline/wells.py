"""Per-well profile and the rules that decide which wells the CSS cycle analysis covers.

Cycle analysis assumes cyclic steam stimulation. Two groups of producers
don't fit that, and one group can't support a fit at all:

- continuous-process wells (SAGD / SA-SAGD): no steam cycles, just a ramp and a
  plateau, at rates an order of magnitude above CSS wells
- wells with too little history to hold even one decline fit
- wells below the minimum-volume filter (see cycles.py)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from petro_decline.cycles import MIN_WELL_VOLUME_M3
from petro_decline.data import OIL_LIKE_PRODUCTS, well_oil_series

MIN_HISTORY_MONTHS = 6

# CSS wells here top out around 2,500 m3/month on average and all shut in for
# steaming at some point; the SA-SAGD pad runs 3,500+ with no shut-in at all.
CONTINUOUS_MIN_MEAN_M3 = 3000
CONTINUOUS_MIN_PRODUCING_MONTHS = 12

# Wells first reported in the opening months of the data are mostly wells
# already producing (late reporters, returns from suspension). Only wells
# that first appear after this settling period are treated as new.
SETTLING_MONTHS = 6


def _shut_in_months(values: np.ndarray) -> int:
    """Zero months between a well's first and last producing month."""
    producing = np.flatnonzero(values > 0)
    if len(producing) == 0:
        return 0
    return int((values[producing[0] : producing[-1] + 1] == 0).sum())


def well_profile(well_level: pd.DataFrame) -> pd.DataFrame:
    """One row per producer well, with start date, rate, shut-in count and the flags below.

    new_in_window: first reported after the settling period, so its cycle
        numbers are real lifetime numbers rather than counts from the data start
    is_redrill: the well ID's event suffix isn't 00 (a sidetrack or re-entry)
    process: 'continuous' or 'css'
    excluded_reason: why the well is left out of cycle analysis ('' if kept)
    """
    window_start = well_level["ProductionMonth"].min()
    window_end = well_level["ProductionMonth"].max()
    settled = window_start + pd.DateOffset(months=SETTLING_MONTHS)

    producers = well_level[~well_level["IsInjector"]]
    first_reported = producers.groupby("FromToID")["ProductionMonth"].min()
    oil_wells = producers.loc[producers["ProductID"].isin(OIL_LIKE_PRODUCTS), "FromToID"].unique()

    rows = []
    for well_id in oil_wells:
        series = well_oil_series(well_level, well_id)
        values = series.to_numpy()
        producing = values[values > 0]
        first = first_reported[well_id]
        history = (window_end.year - first.year) * 12 + (window_end.month - first.month) + 1
        shut_in = _shut_in_months(values)
        mean_rate = float(producing.mean()) if len(producing) else 0.0

        is_continuous = (
            mean_rate >= CONTINUOUS_MIN_MEAN_M3 and len(producing) >= CONTINUOUS_MIN_PRODUCING_MONTHS and shut_in == 0
        )
        if is_continuous:
            reason = "continuous process"
        elif history < MIN_HISTORY_MONTHS:
            reason = f"under {MIN_HISTORY_MONTHS} months of history"
        elif values.max() <= MIN_WELL_VOLUME_M3:
            reason = "below minimum volume"
        else:
            reason = ""

        rows.append(
            {
                "FromToID": well_id,
                "first_reported": first,
                "history_months": history,
                "producing_months": len(producing),
                "shut_in_months": shut_in,
                "mean_producing_m3": round(mean_rate, 1),
                "new_in_window": first >= settled,
                "is_redrill": well_id[-2:] != "00",
                "process": "continuous" if is_continuous else "css",
                "excluded_reason": reason,
            }
        )
    return pd.DataFrame(rows)
