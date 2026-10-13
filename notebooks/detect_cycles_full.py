"""Cycle detection across every eligible producer well, both batteries.

Eligibility comes from petro_decline.wells.well_profile: continuous-process
(SA-SAGD) wells, wells with under six months of history and wells below the
minimum volume are left out. Plant-outage months are interpolated before peak
finding so the recovery from a shutdown isn't read as a wave of re-steams.

Run with: python notebooks/detect_cycles_full.py

Outputs to notebooks/output/:
  - cycles_full.csv        one row per detected cycle
  - near_misses_full.csv   one row per near-miss candidate peak
  - well_profiles.csv      every producer well with its flags and exclusion reason
  - outage_months.csv      battery-wide outage months that were masked
  - summary.txt            counts referenced in the printed summary
  - example plots for the wells with the most near-miss / short-cycle flags
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from explore_cycle_detection import battery_slug, load_well_level, plot_cycle_detection  # noqa: E402
from petro_decline.cycles import DEFAULT_SETTINGS, SHORT_CYCLE_MONTHS, DetectionSettings, detect_cycles  # noqa: E402
from petro_decline.data import TARGET_BATTERIES, well_oil_series  # noqa: E402
from petro_decline.outages import fill_outages, find_outage_months  # noqa: E402
from petro_decline.wells import well_profile  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
N_EXAMPLE_WELLS_PER_CATEGORY = 3


def run_full_detection(settings: DetectionSettings = DEFAULT_SETTINGS):
    """Detect cycles for every eligible well.

    Returns (cycles_df, near_misses_df, profiles_df, outages_df), long-format
    tables with a Battery column.
    """
    cycle_rows, near_miss_rows, profile_frames, outage_rows = [], [], [], []

    for facility_id, name in TARGET_BATTERIES.items():
        well_level = load_well_level(name)
        profile = well_profile(well_level)
        profile.insert(0, "Battery", name)
        profile_frames.append(profile)

        outages = find_outage_months(well_level)
        outage_rows.extend({"Battery": name, "Month": month} for month in outages)

        kept = profile.loc[profile["excluded_reason"] == "", "FromToID"]
        print(f"{name}: {len(profile)} producer wells, {len(kept)} eligible, {len(outages)} outage month(s) masked")

        for well_id in kept:
            series = fill_outages(well_oil_series(well_level, well_id), outages)
            result = detect_cycles(series, settings)
            for cycle in result["cycles"]:
                cycle_rows.append({"Battery": name, "FromToID": well_id, **cycle})
            for month in result["near_misses"]:
                near_miss_rows.append({"Battery": name, "FromToID": well_id, "Month": month})

    return (
        pd.DataFrame(cycle_rows),
        pd.DataFrame(near_miss_rows),
        pd.concat(profile_frames, ignore_index=True),
        pd.DataFrame(outage_rows),
    )


def summarize(cycles_df: pd.DataFrame, near_misses_df: pd.DataFrame, profiles_df: pd.DataFrame) -> str:
    total_wells = cycles_df[["Battery", "FromToID"]].drop_duplicates().shape[0]
    wells_with_near_miss = near_misses_df[["Battery", "FromToID"]].drop_duplicates().shape[0]

    short_cycles = cycles_df[cycles_df["short_cycle"]]
    fittable_cycles = cycles_df[~cycles_df["is_startup_ramp"]]

    lines = ["=== Well eligibility ==="]
    for battery, group in profiles_df.groupby("Battery"):
        reasons = group["excluded_reason"].replace("", "kept").value_counts()
        lines.append(f"  {battery}: {len(group)} producer wells -> " + ", ".join(f"{n} {r}" for r, n in reasons.items()))
    lines += [
        "",
        f"Wells analyzed: {total_wells}",
        f"Total cycles detected: {len(cycles_df)} ({len(cycles_df) - len(fittable_cycles)} startup ramps, "
        f"{len(fittable_cycles)} fittable)",
        f"Wells with >=1 near-miss candidate: {wells_with_near_miss} ({100 * wells_with_near_miss / total_wells:.1f}%)",
        f"Short cycles (<{SHORT_CYCLE_MONTHS} months): {len(short_cycles)} of {len(cycles_df)}",
    ]
    return "\n".join(lines)


def plot_examples(well_level_cache: dict[str, pd.DataFrame], wells: list[tuple[str, str]], label: str) -> None:
    for battery_name, well_id in wells:
        well_level = well_level_cache[battery_name]
        series = fill_outages(well_oil_series(well_level, well_id), find_outage_months(well_level))
        result = detect_cycles(series)
        outpath = OUTPUT_DIR / f"{label}_{battery_slug(battery_name)}_{well_id}.png"
        plot_cycle_detection(well_id, series, result["cycle_starts"], battery_name, outpath, result["near_misses"])
        print(f"  Saved {outpath}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cycles_df, near_misses_df, profiles_df, outages_df = run_full_detection()
    cycles_df.to_csv(OUTPUT_DIR / "cycles_full.csv", index=False)
    near_misses_df.to_csv(OUTPUT_DIR / "near_misses_full.csv", index=False)
    profiles_df.to_csv(OUTPUT_DIR / "well_profiles.csv", index=False)
    outages_df.to_csv(OUTPUT_DIR / "outage_months.csv", index=False)

    summary_text = summarize(cycles_df, near_misses_df, profiles_df)
    print()
    print(summary_text)
    (OUTPUT_DIR / "summary.txt").write_text(summary_text, encoding="utf-8")

    well_level_cache = {name: load_well_level(name) for name in TARGET_BATTERIES.values()}

    near_miss_counts = near_misses_df.groupby(["Battery", "FromToID"]).size().sort_values(ascending=False)
    top_near_miss_wells = near_miss_counts.head(N_EXAMPLE_WELLS_PER_CATEGORY).index.tolist()
    print(f"\nPlotting {len(top_near_miss_wells)} example wells with the most near-miss flags:")
    plot_examples(well_level_cache, top_near_miss_wells, "near_miss_example")

    short_counts = cycles_df[cycles_df["short_cycle"]].groupby(["Battery", "FromToID"]).size().sort_values(ascending=False)
    top_short_cycle_wells = short_counts.head(N_EXAMPLE_WELLS_PER_CATEGORY).index.tolist()
    print(f"\nPlotting {len(top_short_cycle_wells)} example wells with the most short-cycle flags:")
    plot_examples(well_level_cache, top_short_cycle_wells, "short_cycle_example")


if __name__ == "__main__":
    main()
