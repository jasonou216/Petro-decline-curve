"""Full-population cycle detection across every producer well, both batteries.

Runs `detect_cycles` (see explore_cycle_detection.py) across every producer
well in Mahihkan and Nabiye, using the relative-prominence settings validated
on the 10-well sample (MIN_RELATIVE_PROMINENCE_FRACTION=0.4). Does not fit
anything and does not decide any inclusion/exclusion — outputs full diagnostic
tables plus a handful of example plots so patterns can be reviewed across the
whole well set rather than guessed from a handful of samples.

Run with: python notebooks/detect_cycles_full.py

Outputs to notebooks/output/:
  - cycles_full.csv        one row per detected cycle, all wells
  - near_misses_full.csv   one row per near-miss candidate peak, all wells
  - summary.txt            counts referenced in the printed summary
  - example plots for the wells with the most near-miss / short-cycle flags
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from explore_cycle_detection import (  # noqa: E402
    MIN_WELL_VOLUME_M3,
    SHORT_CYCLE_MONTHS,
    battery_slug,
    detect_cycles,
    load_well_level,
    passes_volume_filter,
    plot_cycle_detection,
    well_oil_series,
)
from petro_decline.data import TARGET_BATTERIES  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
N_EXAMPLE_WELLS_PER_CATEGORY = 3


def run_full_detection() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Run cycle detection across every producer well in both batteries.

    Wells whose OIL never exceeds MIN_WELL_VOLUME_M3 are excluded before
    detection runs at all — cycle detection on that little signal is fitting
    noise, not finding real re-stimulations.

    Returns (cycles_df, near_misses_df, volume_filter_counts) — the two
    long-format tables (one detected cycle per row, one near-miss candidate
    per row) plus a {battery_name: (total_producers, excluded_by_volume)}
    dict for the summary.
    """
    cycle_rows = []
    near_miss_rows = []
    volume_filter_counts = {}

    for facility_id, name in TARGET_BATTERIES.items():
        well_level = load_well_level(name)
        all_producer_ids = well_level.loc[~well_level["IsInjector"], "FromToID"].unique()
        well_series = {well_id: well_oil_series(well_level, well_id) for well_id in all_producer_ids}
        kept_producer_ids = [well_id for well_id, series in well_series.items() if passes_volume_filter(series)]

        excluded_count = len(all_producer_ids) - len(kept_producer_ids)
        volume_filter_counts[name] = (len(all_producer_ids), excluded_count)
        print(
            f"{name}: {len(all_producer_ids)} producer wells, {excluded_count} excluded "
            f"(OIL never exceeds {MIN_WELL_VOLUME_M3} m3/month) -> "
            f"detecting cycles across {len(kept_producer_ids)} wells..."
        )

        for well_id in kept_producer_ids:
            series = well_series[well_id]
            result = detect_cycles(series)

            for cycle in result["cycles"]:
                cycle_rows.append({"Battery": name, "FromToID": well_id, **cycle})
            for month in result["near_misses"]:
                near_miss_rows.append({"Battery": name, "FromToID": well_id, "Month": month})

    cycles_df = pd.DataFrame(cycle_rows)
    near_misses_df = pd.DataFrame(near_miss_rows)
    return cycles_df, near_misses_df, volume_filter_counts


def summarize(cycles_df: pd.DataFrame, near_misses_df: pd.DataFrame, volume_filter_counts: dict) -> str:
    total_wells = cycles_df[["Battery", "FromToID"]].drop_duplicates().shape[0]
    wells_with_near_miss = near_misses_df[["Battery", "FromToID"]].drop_duplicates().shape[0]

    short_cycles = cycles_df[cycles_df["short_cycle"]]
    wells_with_short_cycle = short_cycles[["Battery", "FromToID"]].drop_duplicates().shape[0]
    short_final_only = short_cycles.groupby(["Battery", "FromToID"])["is_final_cycle"].all()
    wells_short_final_only = int(short_final_only.sum())

    startup_ramp_cycles = cycles_df[cycles_df["is_startup_ramp"]]
    fittable_cycles = cycles_df[~cycles_df["is_startup_ramp"]]

    total_producers_before_filter = sum(total for total, _excluded in volume_filter_counts.values())
    total_excluded_by_volume = sum(excluded for _total, excluded in volume_filter_counts.values())

    lines = ["=== Minimum-volume filter (OIL must exceed 50 m3/month at least once) ==="]
    for battery_name, (total, excluded) in volume_filter_counts.items():
        lines.append(f"  {battery_name}: {total} producer wells, {excluded} excluded ({total - excluded} kept)")
    lines.append(
        f"  Combined: {total_producers_before_filter} producer wells -> "
        f"{total_excluded_by_volume} excluded -> {total_wells} analyzed"
    )
    lines.append("")

    lines.extend(
        [
            f"Total producer wells analyzed (post volume filter): {total_wells}",
            f"Total cycles detected: {len(cycles_df)}",
            "",
            f"Startup-ramp cycles (each well's first cycle, flagged not fit): {len(startup_ramp_cycles)}",
            f"Fittable cycles remaining for Phase 3: {len(fittable_cycles)}",
            "",
            f"Wells with >=1 near-miss candidate (30-40% relative rise, rejected): "
            f"{wells_with_near_miss} ({100 * wells_with_near_miss / total_wells:.1f}%)",
            f"Total near-miss candidate peaks: {len(near_misses_df)}",
            "",
            f"Wells with >=1 short cycle (<{SHORT_CYCLE_MONTHS} months): "
            f"{wells_with_short_cycle} ({100 * wells_with_short_cycle / total_wells:.1f}%)",
            f"  ...of which, only short because their *final* (right-censored, still-ongoing) "
            f"cycle is short: {wells_short_final_only} wells — not necessarily a detection problem",
            f"  ...wells with a short cycle *before* the final one (more likely a real issue): "
            f"{wells_with_short_cycle - wells_short_final_only} wells",
            f"Total short cycles detected: {short_cycles.shape[0]} out of {len(cycles_df)} total cycles",
        ]
    )
    return "\n".join(lines)


def plot_examples(well_level_cache: dict[str, pd.DataFrame], wells: list[tuple[str, str]], label: str) -> None:
    for battery_name, well_id in wells:
        well_level = well_level_cache[battery_name]
        series = well_oil_series(well_level, well_id)
        result = detect_cycles(series)
        outpath = OUTPUT_DIR / f"{label}_{battery_slug(battery_name)}_{well_id}.png"
        plot_cycle_detection(well_id, series, result["cycle_starts"], battery_name, outpath, result["near_misses"])
        print(f"  Saved {outpath}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cycles_df, near_misses_df, volume_filter_counts = run_full_detection()
    cycles_df.to_csv(OUTPUT_DIR / "cycles_full.csv", index=False)
    near_misses_df.to_csv(OUTPUT_DIR / "near_misses_full.csv", index=False)

    summary_text = summarize(cycles_df, near_misses_df, volume_filter_counts)
    print()
    print(summary_text)
    (OUTPUT_DIR / "summary.txt").write_text(summary_text, encoding="utf-8")

    well_level_cache = {name: load_well_level(name) for name in TARGET_BATTERIES.values()}

    near_miss_counts = near_misses_df.groupby(["Battery", "FromToID"]).size().sort_values(ascending=False)
    top_near_miss_wells = near_miss_counts.head(N_EXAMPLE_WELLS_PER_CATEGORY).index.tolist()
    print(f"\nPlotting {len(top_near_miss_wells)} example wells with the most near-miss flags:")
    plot_examples(well_level_cache, top_near_miss_wells, "near_miss_example")

    short_cycles = cycles_df[cycles_df["short_cycle"]]
    short_cycle_counts = short_cycles.groupby(["Battery", "FromToID"]).size().sort_values(ascending=False)
    top_short_cycle_wells = short_cycle_counts.head(N_EXAMPLE_WELLS_PER_CATEGORY).index.tolist()
    print(f"\nPlotting {len(top_short_cycle_wells)} example wells with the most short-cycle flags:")
    plot_examples(well_level_cache, top_short_cycle_wells, "short_cycle_example")


if __name__ == "__main__":
    main()
