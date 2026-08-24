"""Cycle-detection sandbox for per-well CSS decline analysis.

Phase 2 findings ruled out pad-level Arps fitting: Mahihkan's pad-level aggregate
is a flat plateau (individual well cycles cancel out when summed) and Nabiye's
aggregate rise is driven by new wells coming online, not per-well decline. The
new approach fits Arps to individual production *cycles* within each well
(steam stimulation -> decline -> next stimulation), instead of to a pad-level
series or to a whole well's raw history.

This script only detects cycle boundaries on a handful of sample wells and
plots them for visual review — it does not fit anything and does not run
across the full well set. Run with: python notebooks/explore_cycle_detection.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from scipy.signal import find_peaks

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from petro_decline.data import TARGET_BATTERIES, well_oil_series  # noqa: E402

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Peak-detection tuning: a "new cycle" peak must be at least this many months
# after the previous one (a CSS steam/soak/produce cycle rarely repeats faster
# than this). Prominence is judged *relative to each candidate peak's own
# height* (not the well's all-time max) — a peak must rise at least this
# fraction above its own topographic base (scipy's prominence, which already
# finds the right local trough/saddle) to count as a fresh stimulation. Using
# the well's global max as the yardstick was tried first and rejected: cycle
# amplitude commonly fades over a well's life, so later/smaller cycles never
# cleared a bar set by the well's single biggest cycle and were silently
# merged into whatever cycle preceded them. Both constants are starting
# guesses for visual review, not tuned.
MIN_CYCLE_SPACING_MONTHS = 4
MIN_RELATIVE_PROMINENCE_FRACTION = 0.4

# Candidate peaks in this band cleared distance/prominence-floor checks but fell
# short of MIN_RELATIVE_PROMINENCE_FRACTION — close enough to the cutoff to flag
# for review rather than silently discard.
NEAR_MISS_LOWER_FRACTION = 0.3

# Cycles shorter than this are flagged for visual review before Phase 3 trusts
# them for Arps fitting — right at the edge of what a 4-month minimum peak
# spacing can reliably distinguish from noise.
SHORT_CYCLE_MONTHS = 6

# Wells whose OIL never exceeds this rate are excluded entirely: at this scale
# cycle detection is essentially fitting noise (confirmed by hand-review —
# e.g. ABWI105022306504W400, ABWI104070806504W400).
MIN_WELL_VOLUME_M3 = 50

N_SAMPLE_WELLS_PER_BATTERY = 5


def battery_slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def load_well_level(name: str) -> pd.DataFrame:
    df = pd.read_csv(PROCESSED_DIR / f"{battery_slug(name)}_well_level.csv")
    df["ProductionMonth"] = pd.to_datetime(df["ProductionMonth"])
    return df


def passes_volume_filter(series: pd.Series) -> bool:
    """True if a well's OIL rate exceeds MIN_WELL_VOLUME_M3 at least once."""
    return series.max() > MIN_WELL_VOLUME_M3


def _month_span(start: pd.Timestamp, end: pd.Timestamp) -> int:
    """Inclusive number of months from start to end (both counted)."""
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def detect_cycles(series: pd.Series) -> dict:
    """Detect cycle starts in an OIL series, with near-miss and short-cycle diagnostics.

    A fresh steam stimulation shows up as a local peak in the OIL series (rate
    jumps up, then declines until the next stimulation). The series' first
    month is always included as the start of the first observed cycle, since
    scipy can't call it a "peak" with no prior neighbor to compare against —
    note this first "cycle" is left-censored for any well that was already
    producing before our data starts (2022-01, the API's own data horizon).

    Returns a dict:
      - "cycle_starts": accepted cycle start months (list[pd.Timestamp])
      - "near_misses": candidate peaks with relative prominence in
        [NEAR_MISS_LOWER_FRACTION, MIN_RELATIVE_PROMINENCE_FRACTION) — close to
        the cutoff but rejected (list[pd.Timestamp])
      - "cycles": one row per accepted cycle — start, end, duration_months,
        short_cycle (duration < SHORT_CYCLE_MONTHS), is_final_cycle (the last
        cycle is right-censored: the well may still be mid-cycle at the data
        cutoff, so a short final cycle isn't necessarily a detection problem),
        is_startup_ramp (the *first* cycle isn't a post-stimulation decline at
        all — it runs from the well's first reported month, which is often a
        rising value, to the first detected re-stimulation peak, so it's
        initial production coming online rather than a steam re-stim, and
        shouldn't be fit as a decline cycle)
    """
    values = series.to_numpy()
    index = series.index

    if values.max() == 0:
        cycle_starts = [index[0]]
        near_misses = []
    else:
        # tiny floor just to get scipy to compute prominences for real local maxima;
        # the actual filtering happens below, relative to each peak's own height.
        peak_indices, properties = find_peaks(values, distance=MIN_CYCLE_SPACING_MONTHS, prominence=1e-6)
        relative_prominence = properties["prominences"] / values[peak_indices]

        accepted = peak_indices[relative_prominence >= MIN_RELATIVE_PROMINENCE_FRACTION]
        near_miss = peak_indices[
            (relative_prominence >= NEAR_MISS_LOWER_FRACTION) & (relative_prominence < MIN_RELATIVE_PROMINENCE_FRACTION)
        ]

        # find_peaks enforces MIN_CYCLE_SPACING_MONTHS between detected peaks, but
        # index[0] is a forced cycle start, not a detected peak, so that spacing
        # guard never applied to it. If the first accepted peak lands within the
        # same minimum spacing of index[0], merge it into the forced first cycle
        # instead of creating a second cycle start almost on top of the first.
        if len(accepted) > 0 and accepted[0] < MIN_CYCLE_SPACING_MONTHS:
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


def detect_cycle_starts(series: pd.Series) -> list[pd.Timestamp]:
    """Cycle start months only — thin wrapper around `detect_cycles` for plotting."""
    return detect_cycles(series)["cycle_starts"]


def pick_sample_wells(well_level: pd.DataFrame, n: int) -> list[str]:
    """Pick producer wells with the longest OIL history — most likely to show multiple cycles."""
    producer_oil = well_level[(~well_level["IsInjector"]) & (well_level["ProductID"] == "OIL")]
    months = producer_oil.groupby("FromToID")["ProductionMonth"].nunique().sort_values(ascending=False)
    return months.head(n).index.tolist()


def plot_cycle_detection(
    well_id: str,
    series: pd.Series,
    cycle_starts: list[pd.Timestamp],
    battery_name: str,
    outpath: Path,
    near_misses: list[pd.Timestamp] | None = None,
) -> None:
    fig, ax = plt.subplots(figsize=(11, 3.5))
    ax.plot(series.index, series.values, marker="o", markersize=3, label="OIL (m3/month)")
    for i, start in enumerate(cycle_starts):
        ax.axvline(start, color="red", linestyle="--", alpha=0.6, label="cycle start" if i == 0 else None)
    for i, month in enumerate(near_misses or []):
        ax.axvline(month, color="orange", linestyle=":", alpha=0.8, label="near-miss (30-40%)" if i == 0 else None)
    ax.set_title(f"{battery_name} — {well_id} ({len(cycle_starts)} cycle(s) detected)")
    ax.set_ylabel("OIL (m3/month)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for facility_id, name in TARGET_BATTERIES.items():
        well_level = load_well_level(name)
        wells = pick_sample_wells(well_level, N_SAMPLE_WELLS_PER_BATTERY)
        print(f"{name}: sampling {wells}")

        for well_id in wells:
            series = well_oil_series(well_level, well_id)
            cycle_starts = detect_cycle_starts(series)
            outpath = OUTPUT_DIR / f"cycles_{battery_slug(name)}_{well_id}.png"
            plot_cycle_detection(well_id, series, cycle_starts, name, outpath)
            starts_str = [d.strftime("%Y-%m") for d in cycle_starts]
            print(f"  {well_id}: {len(cycle_starts)} cycle(s) starting at {starts_str}")


if __name__ == "__main__":
    main()
