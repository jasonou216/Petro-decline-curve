"""Star-schema CSV exports for the Power BI companion report.

Reuses the already-computed pipeline outputs (cycles_full.csv,
decline_fits_full.csv, decline_economics_full.csv) rather than recomputing
anything, same convention as economics.py and app.py: this module only
reshapes what notebooks/detect_cycles_full.py, fit_declines_full.py, and
economics_full.py already produced.

Run with: python -m petro_decline.bi_export
(requires the full pipeline above to have already run)

Outputs to bi_exports/:
  dim_battery.csv  one row per battery
  dim_well.csv     one row per well that went through cycle detection
  fact_cycle.csv   one row per fittable cycle, the table Power BI measures
                   are built against
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
NOTEBOOK_OUTPUT_DIR = _PROJECT_ROOT / "notebooks" / "output"
BI_EXPORT_DIR = _PROJECT_ROOT / "bi_exports"

# Not tracked anywhere else in the codebase (TARGET_BATTERIES only maps a
# facility ID to a battery name) — both batteries are Imperial Oil, per the
# README's battery table.
BATTERY_OPERATORS = {
    "Mahihkan Battery 02-21": "Imperial Oil",
    "Nabiye 11-23": "Imperial Oil",
}


def build_dim_well(cycles: pd.DataFrame, fits: pd.DataFrame) -> pd.DataFrame:
    """One row per well that went through cycle detection — the same well
    universe as the dashboard's "wells analyzed" count (every well in
    cycles_full.csv, not just wells with a fittable or high-confidence
    cycle). A well with zero fittable cycles (e.g. startup-ramp-only) gets
    0 for both cycle counts rather than being dropped.
    """
    well_universe = cycles[["Battery", "FromToID"]].drop_duplicates()

    per_well = (
        fits.groupby(["Battery", "FromToID"])
        .agg(
            TotalCycles=("cycle_number", "count"),
            TotalHighConfidenceCycles=("low_confidence", lambda flags: int((~flags).sum())),
        )
        .reset_index()
    )

    dim_well = well_universe.merge(per_well, on=["Battery", "FromToID"], how="left")
    dim_well["TotalCycles"] = dim_well["TotalCycles"].fillna(0).astype(int)
    dim_well["TotalHighConfidenceCycles"] = dim_well["TotalHighConfidenceCycles"].fillna(0).astype(int)

    return (
        dim_well.rename(columns={"FromToID": "WellID"})
        .sort_values(["Battery", "WellID"])
        .reset_index(drop=True)[["WellID", "Battery", "TotalCycles", "TotalHighConfidenceCycles"]]
    )


def build_dim_battery(dim_well: pd.DataFrame) -> pd.DataFrame:
    """One row per battery. Both cycle averages are kept, and labeled
    differently, since "avg cycles per well" is ambiguous on its own —
    the dashboard's own headline number is the high-confidence average.
    """
    rows = []
    for battery, group in dim_well.groupby("Battery"):
        rows.append(
            {
                "Battery": battery,
                "Operator": BATTERY_OPERATORS.get(battery, "Unknown"),
                "TotalWells": len(group),
                "AvgCyclesPerWell": round(group["TotalCycles"].mean(), 2),
                "AvgHighConfidenceCyclesPerWell": round(group["TotalHighConfidenceCycles"].mean(), 2),
            }
        )
    return pd.DataFrame(rows).sort_values("Battery").reset_index(drop=True)


def build_fact_cycle(fits: pd.DataFrame, econ: pd.DataFrame) -> pd.DataFrame:
    """One row per fittable cycle (startup ramps already excluded in
    decline_fits_full.csv). EUR/NPV come from decline_economics_full.csv,
    which only has rows for high-confidence cycles — a low-confidence
    cycle gets a blank EUR/NPV here, exactly like the dashboard never
    prices one.
    """
    econ_cols = econ[["Battery", "FromToID", "cycle_number", "EUR", "NPV"]]
    merged = fits.merge(econ_cols, on=["Battery", "FromToID", "cycle_number"], how="left")

    fact_cycle = pd.DataFrame(
        {
            "WellID": merged["FromToID"],
            "Battery": merged["Battery"],
            "CycleNumber": merged["cycle_number"],
            "CycleStart": merged["cycle_start"],
            "DurationMonths": merged["duration_months"],
            "Model": merged["model"],
            "Qi": merged["qi"],
            "Di": merged["Di"],
            "B": merged["b"],
            "RSquared": merged["r_squared"],
            "IsHighConfidence": ~merged["low_confidence"],
            "LowConfidenceReason": merged["low_confidence_reason"],
            "EUR": merged["EUR"],
            "NPV": merged["NPV"],
        }
    )
    return fact_cycle.sort_values(["Battery", "WellID", "CycleNumber"]).reset_index(drop=True)


def main() -> None:
    BI_EXPORT_DIR.mkdir(exist_ok=True)

    cycles = pd.read_csv(NOTEBOOK_OUTPUT_DIR / "cycles_full.csv")
    fits = pd.read_csv(NOTEBOOK_OUTPUT_DIR / "decline_fits_full.csv")
    econ = pd.read_csv(NOTEBOOK_OUTPUT_DIR / "decline_economics_full.csv")

    dim_well = build_dim_well(cycles, fits)
    dim_battery = build_dim_battery(dim_well)
    fact_cycle = build_fact_cycle(fits, econ)

    dim_battery.to_csv(BI_EXPORT_DIR / "dim_battery.csv", index=False)
    dim_well.to_csv(BI_EXPORT_DIR / "dim_well.csv", index=False)
    fact_cycle.to_csv(BI_EXPORT_DIR / "fact_cycle.csv", index=False)

    print(f"dim_battery.csv: {len(dim_battery)} rows -> {BI_EXPORT_DIR / 'dim_battery.csv'}")
    print(f"dim_well.csv: {len(dim_well)} rows -> {BI_EXPORT_DIR / 'dim_well.csv'}")
    print(f"fact_cycle.csv: {len(fact_cycle)} rows -> {BI_EXPORT_DIR / 'fact_cycle.csv'}")


if __name__ == "__main__":
    main()
