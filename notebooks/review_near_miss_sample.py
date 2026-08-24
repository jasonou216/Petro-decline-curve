"""Random sample of near-miss candidates, plotted in full well context for review.

Pulls a reproducible random sample of individual near-miss candidate peaks
(not wells) from notebooks/output/near_misses_full.csv and plots each one
against its well's full OIL history, in the same style as the earlier review
plots (cycle starts in red, all of that well's near-misses in orange) — with
the specific sampled candidate additionally marked, since a well can have
more than one near-miss and the sample is over individual candidates.

Run with: python notebooks/review_near_miss_sample.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from explore_cycle_detection import battery_slug, detect_cycles, load_well_level, well_oil_series  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
REVIEW_DIR = OUTPUT_DIR / "near_miss_review_sample"

SAMPLE_SIZE = 25
RANDOM_SEED = 42


def plot_reviewed_candidate(
    well_id: str,
    series: pd.Series,
    cycle_starts: list[pd.Timestamp],
    near_misses: list[pd.Timestamp],
    reviewed_month: pd.Timestamp,
    battery_name: str,
    outpath: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(11, 3.5))
    ax.plot(series.index, series.values, marker="o", markersize=3, label="OIL (m3/month)")
    for i, start in enumerate(cycle_starts):
        ax.axvline(start, color="red", linestyle="--", alpha=0.6, label="cycle start" if i == 0 else None)
    for i, month in enumerate(near_misses):
        ax.axvline(month, color="orange", linestyle=":", alpha=0.6, label="other near-miss" if i == 0 else None)
    ax.axvline(reviewed_month, color="purple", linestyle="-", linewidth=2, label="near-miss under review")
    ax.set_title(f"{battery_name} — {well_id} — reviewing near-miss at {reviewed_month:%Y-%m}")
    ax.set_ylabel("OIL (m3/month)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


def main() -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    near_misses_df = pd.read_csv(OUTPUT_DIR / "near_misses_full.csv")
    near_misses_df["Month"] = pd.to_datetime(near_misses_df["Month"])
    print(f"Full near-miss population: {len(near_misses_df)} candidates")

    sample = near_misses_df.sample(n=SAMPLE_SIZE, random_state=RANDOM_SEED).reset_index(drop=True)

    well_level_cache: dict[str, pd.DataFrame] = {}

    for i, row in sample.iterrows():
        battery_name, well_id, reviewed_month = row["Battery"], row["FromToID"], row["Month"]

        if battery_name not in well_level_cache:
            well_level_cache[battery_name] = load_well_level(battery_name)
        well_level = well_level_cache[battery_name]

        series = well_oil_series(well_level, well_id)
        result = detect_cycles(series)

        outpath = REVIEW_DIR / f"{i + 1:02d}_{battery_slug(battery_name)}_{well_id}_{reviewed_month:%Y-%m}.png"
        plot_reviewed_candidate(
            well_id, series, result["cycle_starts"], result["near_misses"], reviewed_month, battery_name, outpath
        )
        print(f"  [{i + 1:02d}/{SAMPLE_SIZE}] Saved {outpath}")


if __name__ == "__main__":
    main()
