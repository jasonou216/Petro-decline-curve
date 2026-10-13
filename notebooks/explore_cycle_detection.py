"""Cycle-detection sandbox: plot detected cycle boundaries on a few sample wells.

The detection logic itself lives in src/petro_decline/cycles.py. This script
only draws boundaries on a handful of wells for visual review, it doesn't fit
anything. Run with: python notebooks/explore_cycle_detection.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from petro_decline.cycles import (  # noqa: E402,F401
    MIN_WELL_VOLUME_M3,
    SHORT_CYCLE_MONTHS,
    DetectionSettings,
    detect_cycles,
    passes_volume_filter,
)
from petro_decline.data import TARGET_BATTERIES, well_oil_series  # noqa: E402,F401

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

N_SAMPLE_WELLS_PER_BATTERY = 5


def battery_slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def load_well_level(name: str) -> pd.DataFrame:
    df = pd.read_csv(PROCESSED_DIR / f"{battery_slug(name)}_well_level.csv")
    df["ProductionMonth"] = pd.to_datetime(df["ProductionMonth"])
    return df


def detect_cycle_starts(series: pd.Series) -> list[pd.Timestamp]:
    """Cycle start months only, for plotting."""
    return detect_cycles(series)["cycle_starts"]


def pick_sample_wells(well_level: pd.DataFrame, n: int) -> list[str]:
    """Producer wells with the longest OIL history, most likely to show several cycles."""
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
    ax.set_title(f"{battery_name}, {well_id} ({len(cycle_starts)} cycle(s) detected)")
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
