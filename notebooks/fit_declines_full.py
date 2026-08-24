"""Full-population Arps fitting across every fittable cycle, both batteries.

Runs `petro_decline.decline.fit_all_cycles` across all 6,501 fittable cycles
(is_startup_ramp == False) from notebooks/output/cycles_full.csv, validated
first on a 10-well sample (see notebooks/fit_declines_sample.py). Does not
drop or exclude low-confidence fits — they're kept in the output with the
flag intact, so inclusion in Phase 4's headline stats is a separate decision.

Run with: python notebooks/fit_declines_full.py
(requires notebooks/detect_cycles_full.py to have been run first)

Outputs to notebooks/output/:
  - decline_fits_full.csv     one row per fitted cycle, all wells, both batteries
  - decline_fit_summary.txt   confidence-rate breakdown referenced below
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from explore_cycle_detection import load_well_level  # noqa: E402
from petro_decline import decline  # noqa: E402
from petro_decline.data import TARGET_BATTERIES, well_oil_series  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def build_well_series_by_battery(cycles_df: pd.DataFrame) -> dict[str, dict[str, pd.Series]]:
    """OIL series for every well that appears in cycles_df, grouped by battery."""
    well_level_cache = {name: load_well_level(name) for name in TARGET_BATTERIES.values()}

    well_series_by_battery: dict[str, dict[str, pd.Series]] = {}
    for battery_name, well_ids in cycles_df.groupby("Battery")["FromToID"].unique().items():
        well_level = well_level_cache[battery_name]
        well_series_by_battery[battery_name] = {
            well_id: well_oil_series(well_level, well_id) for well_id in well_ids
        }
    return well_series_by_battery


def confidence_breakdown(fits: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """% low-confidence per value of group_col, plus counts."""
    table = fits.groupby(group_col)["low_confidence"].agg(total="count", low_confidence="sum")
    table["high_confidence"] = table["total"] - table["low_confidence"]
    table["low_confidence_pct"] = (100 * table["low_confidence"] / table["total"]).round(1)
    return table[["total", "high_confidence", "low_confidence", "low_confidence_pct"]]


def summarize(fits: pd.DataFrame) -> str:
    total = len(fits)
    low = int(fits["low_confidence"].sum())
    high = total - low

    lines = [
        "=== Overall ===",
        f"Total fitted cycles: {total}",
        f"High-confidence: {high} ({100 * high / total:.1f}%)",
        f"Low-confidence: {low} ({100 * low / total:.1f}%)",
        "",
        "=== By battery ===",
        confidence_breakdown(fits, "Battery").to_string(),
        "",
        "=== By cycle position (first fittable cycle vs later) ===",
        confidence_breakdown(fits.assign(position=fits["cycle_number"].eq(1).map({True: "first", False: "later"})), "position").to_string(),
        "",
        "=== By cycle duration (short-cycle-flagged vs normal) ===",
        confidence_breakdown(fits.assign(duration_class=fits["short_cycle"].map({True: "short (<6mo)", False: "normal"})), "duration_class").to_string(),
        "",
        "=== Model choice (all cycles) ===",
        fits["model"].value_counts(dropna=False).to_string(),
    ]
    return "\n".join(lines)


def main() -> None:
    cycles_df = pd.read_csv(OUTPUT_DIR / "cycles_full.csv")
    fittable = cycles_df[~cycles_df["is_startup_ramp"]]
    print(f"Fitting {len(fittable)} fittable cycles across {fittable['FromToID'].nunique()} wells...")

    well_series_by_battery = build_well_series_by_battery(fittable)
    fits = decline.fit_all_cycles(cycles_df, well_series_by_battery)
    fits.to_csv(OUTPUT_DIR / "decline_fits_full.csv", index=False)

    summary_text = summarize(fits)
    print()
    print(summary_text)
    (OUTPUT_DIR / "decline_fit_summary.txt").write_text(summary_text, encoding="utf-8")


if __name__ == "__main__":
    main()
