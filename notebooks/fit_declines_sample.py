"""Per-cycle Arps fitting on the same sample wells used in the cycle-detection review.

Runs `petro_decline.decline.fit_all_cycles` against the fittable cycles
(is_startup_ramp == False) of the 10 sample wells from
notebooks/explore_cycle_detection.py (5 Mahihkan + 5 Nabiye, picked by
longest OIL history), and plots each well's raw production with cycle
boundaries and the fitted decline curve overlaid on every cycle — for visual
review before running Arps fitting across all 6,501 fittable cycles.

Run with: python notebooks/fit_declines_sample.py
(requires notebooks/detect_cycles_full.py to have been run first, so
notebooks/output/cycles_full.csv exists)
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from explore_cycle_detection import N_SAMPLE_WELLS_PER_BATTERY, battery_slug, load_well_level, pick_sample_wells  # noqa: E402
from petro_decline import decline  # noqa: E402
from petro_decline.data import TARGET_BATTERIES, well_oil_series  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def plot_well_fits(
    well_id: str,
    series: pd.Series,
    all_cycles: pd.DataFrame,
    fitted_cycles: pd.DataFrame,
    battery_name: str,
    outpath: Path,
) -> None:
    """Plot raw production, every detected cycle boundary, and the fitted curve
    on top of each fittable cycle (the startup-ramp cycle gets a boundary line
    like the others, but no fitted curve — it was never fit).
    """
    fig, ax = plt.subplots(figsize=(11, 3.5))
    ax.plot(series.index, series.values, marker="o", markersize=3, color="steelblue", label="OIL (m3/month)", zorder=2)

    for i, cycle_start in enumerate(sorted(pd.to_datetime(all_cycles["start"]))):
        ax.axvline(cycle_start, color="red", linestyle="--", alpha=0.5, label="cycle start" if i == 0 else None)

    for i, row in enumerate(fitted_cycles.itertuples(index=False)):
        if row.model is None:
            continue
        t = np.arange(row.duration_months, dtype=float)
        fitted = decline.predict(t, row.model, row.qi, row.Di, row.b)
        dates = pd.date_range(row.cycle_start, periods=row.duration_months, freq="MS")
        color = "orange" if row.low_confidence else "green"
        label = None
        if i == 0:
            label = "fitted (orange=low_confidence)"
        ax.plot(dates, fitted, color=color, linewidth=2, alpha=0.8, zorder=3, label=label)

    ax.set_title(f"{battery_name} — {well_id}")
    ax.set_ylabel("OIL (m3/month)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


def main() -> None:
    cycles_df = pd.read_csv(OUTPUT_DIR / "cycles_full.csv")

    well_level_cache: dict[str, pd.DataFrame] = {}
    sample_wells: list[tuple[str, str]] = []  # (battery_name, well_id)

    for facility_id, name in TARGET_BATTERIES.items():
        well_level = load_well_level(name)
        well_level_cache[name] = well_level
        wells = pick_sample_wells(well_level, N_SAMPLE_WELLS_PER_BATTERY)
        sample_wells.extend((name, well_id) for well_id in wells)

    print(f"Sample wells ({len(sample_wells)}): {sample_wells}")

    well_series_by_battery: dict[str, dict[str, pd.Series]] = {name: {} for name in TARGET_BATTERIES.values()}
    for battery_name, well_id in sample_wells:
        well_series_by_battery[battery_name][well_id] = well_oil_series(well_level_cache[battery_name], well_id)

    sample_well_ids = {well_id for _battery, well_id in sample_wells}
    sample_cycles = cycles_df[cycles_df["FromToID"].isin(sample_well_ids)].copy()

    fits = decline.fit_all_cycles(sample_cycles, well_series_by_battery)
    fits.to_csv(OUTPUT_DIR / "decline_fits_sample.csv", index=False)

    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 160)
    print()
    print(fits.to_string(index=False))
    print()
    print(f"Total fitted cycles: {len(fits)}")
    print(f"Low-confidence fits: {fits['low_confidence'].sum()} / {len(fits)}")
    print(f"Model choice counts:\n{fits['model'].value_counts(dropna=False)}")

    for battery_name, well_id in sample_wells:
        series = well_series_by_battery[battery_name][well_id]
        well_all_cycles = sample_cycles[sample_cycles["FromToID"] == well_id]
        well_fitted_cycles = fits[fits["FromToID"] == well_id]
        outpath = OUTPUT_DIR / f"decline_fit_{battery_slug(battery_name)}_{well_id}.png"
        plot_well_fits(well_id, series, well_all_cycles, well_fitted_cycles, battery_name, outpath)
        print(f"Saved {outpath}")


if __name__ == "__main__":
    main()
