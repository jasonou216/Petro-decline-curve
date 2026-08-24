"""Sanity-check high-confidence hyperbolic fits with b near the 2.0 ceiling.

Low-confidence fits already flag b pinned within B_BOUNDARY_EPSILON (1e-3) of
a bound as a sign the optimizer is capped rather than converged. This checks
a wider band (b >= 1.7) among fits that passed as *high*-confidence — good
R² doesn't rule out the same "wants to exceed 2, gets capped" pattern, it
would just be a fit that happens to still track the data reasonably despite
being constrained. Plots a sample in the same style as fit_declines_sample.py
(raw data, every detected cycle boundary, fitted curve on every fitted
cycle) for visual review. Does not change anything — diagnostic only.

Run with: python notebooks/review_hyperbolic_boundary.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from explore_cycle_detection import battery_slug, load_well_level  # noqa: E402
from fit_declines_sample import plot_well_fits  # noqa: E402
from petro_decline.data import well_oil_series  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
B_NEAR_BOUND_THRESHOLD = 1.7

# picked for a spread of R2 (lowest 3, a middle one, highest 3) plus the one
# Nabiye case, out of the 16 total high-confidence cycles with b >= 1.7
SAMPLE_WELLS = [
    ("Mahihkan Battery 02-21", "ABWI103130906604W400"),  # R2=0.778, lowest
    ("Mahihkan Battery 02-21", "ABWI105113406504W400"),  # R2=0.784
    ("Mahihkan Battery 02-21", "ABWI104161506504W400"),  # R2=0.807
    ("Nabiye 11-23", "ABWI102021306603W400"),  # R2=0.905, only Nabiye case
    ("Mahihkan Battery 02-21", "ABWI102122206504W400"),  # R2=0.900
    ("Mahihkan Battery 02-21", "ABWI109042206504W400"),  # R2=0.932
    ("Mahihkan Battery 02-21", "ABWI106021006604W400"),  # R2=0.942
    ("Mahihkan Battery 02-21", "ABWI106040306604W400"),  # R2=0.985, highest
]


def main() -> None:
    cycles_df = pd.read_csv(OUTPUT_DIR / "cycles_full.csv")
    fits = pd.read_csv(OUTPUT_DIR / "decline_fits_full.csv")

    near_bound = fits[(fits["model"] == "hyperbolic") & (fits["b"] >= B_NEAR_BOUND_THRESHOLD) & (~fits["low_confidence"])]
    print(f"High-confidence hyperbolic cycles with b >= {B_NEAR_BOUND_THRESHOLD}: {len(near_bound)}")
    print(near_bound[["Battery", "FromToID", "cycle_number", "b", "r_squared"]].sort_values("r_squared").to_string(index=False))
    print()

    well_level_cache = {}
    for battery_name, well_id in SAMPLE_WELLS:
        if battery_name not in well_level_cache:
            well_level_cache[battery_name] = load_well_level(battery_name)
        well_level = well_level_cache[battery_name]

        series = well_oil_series(well_level, well_id)
        well_all_cycles = cycles_df[cycles_df["FromToID"] == well_id]
        well_fitted_cycles = fits[fits["FromToID"] == well_id]

        outpath = OUTPUT_DIR / f"hyperbolic_boundary_{battery_slug(battery_name)}_{well_id}.png"
        plot_well_fits(well_id, series, well_all_cycles, well_fitted_cycles, battery_name, outpath)
        print(f"Saved {outpath}")


if __name__ == "__main__":
    main()
