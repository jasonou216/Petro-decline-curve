"""Cycle detection: find each steam re-stimulation in a well's monthly oil series.

A re-steam shows up as a local peak in the series (rate jumps, then declines
until the next stimulation). Prominence is judged relative to each candidate
peak's own height rather than the well's all-time max: cycle size commonly
fades over a well's life, so a global yardstick silently merges the later,
smaller cycles into the one before them.

Detection only draws boundaries. Fitting lives in decline.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from scipy.signal import find_peaks

SHORT_CYCLE_MONTHS = 6  # cycles shorter than this are flagged for review
MIN_WELL_VOLUME_M3 = 50  # wells whose OIL never exceeds this are skipped, detection would just be fitting noise


@dataclass(frozen=True)
class DetectionSettings:
    """Peak-detection knobs. The defaults are the original starting guesses."""

    min_spacing_months: int = 4
    min_relative_prominence: float = 0.4
    near_miss_lower: float = 0.3  # peaks between this and min_relative_prominence are logged as near misses

    # A real re-steam takes the well offline for the injection and soak
    # (4-6 weeks plus soak), so the months just before the new peak should be
    # at or near zero. If set, a peak only counts when the lowest of the
    # previous `steam_gap_lookback_months` months is at most this fraction of
    # the peak. None means no gap is required.
    steam_gap_max_fraction: float | None = None
    steam_gap_lookback_months: int = 3


DEFAULT_SETTINGS = DetectionSettings()


def passes_volume_filter(series: pd.Series) -> bool:
    """True if a well's OIL exceeds MIN_WELL_VOLUME_M3 in at least one month."""
    return series.max() > MIN_WELL_VOLUME_M3


def _month_span(start: pd.Timestamp, end: pd.Timestamp) -> int:
    """Inclusive number of months from start to end."""
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def _has_steam_gap(values, peak: int, settings: DetectionSettings) -> bool:
    before = values[max(0, peak - settings.steam_gap_lookback_months) : peak]
    return before.size > 0 and before.min() <= settings.steam_gap_max_fraction * values[peak]


def detect_cycles(series: pd.Series, settings: DetectionSettings = DEFAULT_SETTINGS) -> dict:
    """Detect cycle starts in an OIL series.

    The series' first month is always the start of the first observed cycle
    (scipy can't call it a peak with no earlier neighbour). That first
    segment is left-censored for any well already producing when the data
    begins, and it runs from the well's first reported month, often a rising
    value, to the first detected re-stimulation, so it is flagged as a
    startup ramp rather than a decline cycle.

    Returns a dict:
      cycle_starts: accepted cycle start months
      near_misses: rejected peaks with relative prominence in
          [near_miss_lower, min_relative_prominence)
      cycles: one row per cycle with start, end, duration_months,
          short_cycle, is_final_cycle (right-censored, the well may still be
          mid-cycle) and is_startup_ramp
    """
    values = series.to_numpy()
    index = series.index

    if values.max() == 0:
        cycle_starts = [index[0]]
        near_misses = []
    else:
        # tiny prominence floor just so scipy computes prominences; filtering is relative, below
        peak_indices, properties = find_peaks(values, distance=settings.min_spacing_months, prominence=1e-6)
        relative_prominence = properties["prominences"] / values[peak_indices]

        accepted = peak_indices[relative_prominence >= settings.min_relative_prominence]
        near_miss = peak_indices[
            (relative_prominence >= settings.near_miss_lower) & (relative_prominence < settings.min_relative_prominence)
        ]

        if settings.steam_gap_max_fraction is not None:
            accepted = accepted[[_has_steam_gap(values, int(i), settings) for i in accepted]]

        # index[0] is a forced start, so find_peaks' spacing never applied to it;
        # merge a first peak that lands too close into the forced first cycle
        if len(accepted) > 0 and accepted[0] < settings.min_spacing_months:
            accepted = accepted[1:]

        cycle_starts = sorted({index[0]} | {index[i] for i in accepted})
        near_misses = sorted(index[i] for i in near_miss)

    cycles = []
    for i, start in enumerate(cycle_starts):
        is_final_cycle = i == len(cycle_starts) - 1
        end = index[-1] if is_final_cycle else cycle_starts[i + 1] - pd.DateOffset(months=1)
        duration_months = _month_span(start, end)
        cycles.append(
            {
                "start": start,
                "end": end,
                "duration_months": duration_months,
                "short_cycle": duration_months < SHORT_CYCLE_MONTHS,
                "is_final_cycle": is_final_cycle,
                "is_startup_ramp": i == 0,
            }
        )

    return {"cycle_starts": cycle_starts, "near_misses": near_misses, "cycles": cycles}
