"""Phase 5: full-scale economics across all 1,875 high-confidence cycles.

Uses live WTI (via petro_decline.economics.load_assumptions, EIA API with a
config.yaml fallback) and everything else from config.yaml. Validated first
on a 15-cycle sample (see the Phase 5 sample run). Reports the NPV
distribution (not just an aggregate total), a well-level rollup, a price x
discount-rate sensitivity grid that includes live WTI as its own scenario
alongside fixed $50/$70/$90 cases, and a cross-check of whether negative-NPV
cycles skew toward later-cycle, lower-EUR behavior — tying back to the
Phase 4 degradation finding rather than leaving the connection implicit.

Run with: python notebooks/economics_full.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from petro_decline import economics  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def report_npv_distribution(econ: pd.DataFrame) -> list[str]:
    lines = ["=== 1. NPV distribution (all 1,875 high-confidence cycles) ==="]
    lines.append(econ["NPV"].describe().to_string())

    negative = econ[econ["NPV"] < 0]
    positive = econ[econ["NPV"] >= 0]
    lines.append("")
    lines.append(f"Negative NPV: {len(negative)} cycles ({100 * len(negative) / len(econ):.1f}%)")
    lines.append(f"Non-negative NPV: {len(positive)} cycles ({100 * len(positive) / len(econ):.1f}%)")
    lines.append(f"Sum of negative NPV: ${negative['NPV'].sum():,.0f}")
    lines.append(f"Sum of positive NPV: ${positive['NPV'].sum():,.0f}")
    lines.append(f"Net total NPV: ${econ['NPV'].sum():,.0f}")
    return lines


def report_well_level(econ: pd.DataFrame) -> tuple[list[str], pd.DataFrame]:
    wells = economics.well_level_summary(econ)
    lines = ["", "=== 2. Well-level rollup ==="]
    lines.append(f"Total wells: {len(wells)}")
    negative_wells = wells[wells["total_NPV"] < 0]
    lines.append(f"Wells with negative total NPV (all their HC cycles combined): {len(negative_wells)} ({100 * len(negative_wells) / len(wells):.1f}%)")
    lines.append("")
    lines.append("Top 5 wells by total NPV:")
    lines.append(wells.head(5).to_string(index=False))
    lines.append("")
    lines.append("Bottom 5 wells by total NPV:")
    lines.append(wells.tail(5).to_string(index=False))
    return lines, wells


def report_sensitivity(cycles: pd.DataFrame, assumptions: economics.EconomicAssumptions) -> tuple[list[str], pd.DataFrame]:
    live_price = assumptions.wti_price.value
    price_scenarios = {"low_50": 50.0, "mid_70": 70.0, "high_90": 90.0, "live": live_price}
    discount_rates = [0.08, 0.10, 0.15]

    sens = economics.sensitivity_table(cycles, assumptions, price_scenarios, discount_rates)
    lines = ["", "=== 3. WTI x discount-rate sensitivity grid (full scale) ==="]
    lines.append(f"Live WTI at run time: ${live_price:.2f}/bbl (as of {assumptions.wti_price.last_updated})")
    lines.append(sens.to_string(index=False))
    return lines, sens


def report_degradation_crosscheck(econ: pd.DataFrame) -> list[str]:
    lines = ["", "=== 4. Cross-check: does negative NPV skew toward later, lower-EUR cycles? ==="]
    negative = econ[econ["NPV"] < 0]
    positive = econ[econ["NPV"] >= 0]

    for label, group in [("Negative-NPV cycles", negative), ("Non-negative-NPV cycles", positive)]:
        later_share = 100 * (group["cycle_number"] >= 3).sum() / len(group) if len(group) else float("nan")
        lines.append(
            f"{label} (n={len(group)}): median cycle_number={group['cycle_number'].median():.0f}, "
            f"{later_share:.1f}% at position 3rd+, median EUR={group['EUR'].median():.1f} m3"
        )

    lines.append("")
    lines.append("Position breakdown (share of each bucket that's negative NPV):")
    for position_label, mask in [
        ("1st", econ["cycle_number"] == 1),
        ("2nd", econ["cycle_number"] == 2),
        ("3rd+", econ["cycle_number"] >= 3),
    ]:
        bucket = econ[mask]
        neg_pct = 100 * (bucket["NPV"] < 0).sum() / len(bucket) if len(bucket) else float("nan")
        lines.append(f"  {position_label}: {(bucket['NPV'] < 0).sum()} / {len(bucket)} negative ({neg_pct:.1f}%)")

    return lines


def main() -> None:
    assumptions = economics.load_assumptions()
    print()
    assumptions.print_summary()
    print()

    hc = pd.read_csv(OUTPUT_DIR / "high_confidence_cycles_with_eur.csv")
    print(f"Running economics on {len(hc)} high-confidence cycles...")
    econ = economics.compute_cycle_economics(hc, assumptions)
    econ.to_csv(OUTPUT_DIR / "decline_economics_full.csv", index=False)

    report_lines = []
    report_lines.extend(report_npv_distribution(econ))

    well_lines, wells = report_well_level(econ)
    report_lines.extend(well_lines)
    wells.to_csv(OUTPUT_DIR / "well_economics_summary.csv", index=False)

    sens_lines, sens = report_sensitivity(hc, assumptions)
    report_lines.extend(sens_lines)
    sens.to_csv(OUTPUT_DIR / "sensitivity_grid_full.csv", index=False)

    report_lines.extend(report_degradation_crosscheck(econ))

    report_text = "\n".join(report_lines)
    print(report_text)
    (OUTPUT_DIR / "economics_full_report.txt").write_text(report_text, encoding="utf-8")


if __name__ == "__main__":
    main()
