"""Compare Petrinex battery volumes with the bitumen rates Imperial reported to the AER.

Imperial's annual Directive 054 submissions for Cold Lake (AER approval 8558)
give average bitumen production per plant. Mahihkan and Nabiye here are the
Mahihkan and Nabiye plants in those filings. The 2022 operating year is
missing (that submission wasn't available), so only 2023 and 2024 are checked.

Run with: python notebooks/validate_against_filings.py
Writes notebooks/output/filings_validation.txt.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from explore_cycle_detection import load_well_level  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Average bitumen production, m3/d, from the "Facility Performance" slide of
# Imperial's Directive 054 annual submissions (June 2024 for 2023, June 2025 for 2024).
REPORTED_M3_PER_DAY = {
    ("Mahihkan Battery 02-21", 2023): 7924,
    ("Mahihkan Battery 02-21", 2024): 8882,
    ("Nabiye 11-23", 2023): 1950,
    ("Nabiye 11-23", 2024): 4078,
}


def petrinex_rate(battery: str, year: int) -> float:
    """Average m3/d over the year from the battery's monthly OIL volumes."""
    oil = load_well_level(battery)
    oil = oil[(oil["ProductID"] == "OIL") & (oil["ProductionMonth"].dt.year == year)]
    monthly = oil.groupby("ProductionMonth")["Volume"].sum()
    return float(monthly.sum() / monthly.index.days_in_month.to_numpy().sum())


def main() -> None:
    lines = ["battery | year | Petrinex m3/d | reported m3/d | difference"]
    for (battery, year), reported in REPORTED_M3_PER_DAY.items():
        ours = petrinex_rate(battery, year)
        lines.append(f"{battery} | {year} | {ours:,.0f} | {reported:,} | {ours / reported - 1:+.1%}")
    report = "\n".join(lines)
    print(report)
    (OUTPUT_DIR / "filings_validation.txt").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
