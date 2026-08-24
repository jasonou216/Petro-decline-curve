"""Exploratory analysis of pulled Cold Lake production data (Mahihkan vs Nabiye).

Run with: python notebooks/explore_production.py
(requires `python -m petro_decline.data ...` to have been run first, so
data/processed/ is populated)

Throwaway exploration, not part of the src/petro_decline pipeline: makes no
inclusion/exclusion decisions, just visualizes the pulled data and flags things
worth a second look. Writes plots + a text report to notebooks/output/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from petro_decline.data import TARGET_BATTERIES  # noqa: E402

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

PRODUCTS = ["OIL", "GAS", "WATER"]

# thresholds for flag_data_quality — exploratory heuristics, not tuned/validated
STEP_CHANGE_THRESHOLD = 0.5  # 50% month-over-month change
FLAT_WINDOW_MONTHS = 3
FLAT_STD_FRACTION = 0.01  # rolling std below 1% of series mean counts as "flat"


def battery_slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def load_well_level(name: str) -> pd.DataFrame:
    df = pd.read_csv(PROCESSED_DIR / f"{battery_slug(name)}_well_level.csv")
    df["ProductionMonth"] = pd.to_datetime(df["ProductionMonth"])
    return df


def load_pad_level(name: str) -> pd.DataFrame:
    df = pd.read_csv(PROCESSED_DIR / f"{battery_slug(name)}_pad_level.csv")
    df["ProductionMonth"] = pd.to_datetime(df["ProductionMonth"])
    return df


def pick_sample_wells(well_level: pd.DataFrame, target_total: int = 5, max_injectors: int = 2) -> list[str]:
    """Pick a few injector-flagged wells plus a few high-volume, long-history producers.

    Producers are filtered to >=12 months of OIL history first, so a well with
    only a couple of scattered data points doesn't get picked just for having a
    high average.
    """
    injector_ids = list(well_level.loc[well_level["IsInjector"], "FromToID"].unique())
    n_injectors = min(max_injectors, len(injector_ids))
    n_producers = target_total - n_injectors

    producer_oil = well_level[(~well_level["IsInjector"]) & (well_level["ProductID"] == "OIL")]
    producer_totals = producer_oil.groupby("FromToID").agg(months=("ProductionMonth", "nunique"), total_oil=("Volume", "sum"))
    producer_totals = producer_totals[producer_totals["months"] >= 12]
    producer_ids = producer_totals.sort_values("total_oil", ascending=False).head(n_producers).index.tolist()

    return injector_ids[:n_injectors] + producer_ids


def plot_well_sawtooth(well_level: pd.DataFrame, well_ids: list[str], battery_name: str, outpath: Path) -> None:
    fig, axes = plt.subplots(len(well_ids), 1, figsize=(10, 2.3 * len(well_ids)), sharex=True)
    if len(well_ids) == 1:
        axes = [axes]
    for ax, well_id in zip(axes, well_ids):
        well_df = well_level[well_level["FromToID"] == well_id]
        is_injector = bool(well_df["IsInjector"].iloc[0]) if not well_df.empty else False
        for product in PRODUCTS:
            series = well_df[well_df["ProductID"] == product].sort_values("ProductionMonth")
            if not series.empty:
                ax.plot(series["ProductionMonth"], series["Volume"], marker="o", markersize=2, label=product)
        tag = "INJECTOR-FLAGGED (zero OIL/BIT all history)" if is_injector else "producer"
        ax.set_title(f"{well_id} — {tag}", fontsize=9)
        ax.legend(fontsize=7, loc="upper right")
        ax.grid(alpha=0.3)
    fig.suptitle(f"{battery_name}: individual well monthly volumes (CSS cycling check)")
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


def plot_pad_level_comparison(pad_level_data: dict[str, pd.DataFrame], outpath: Path) -> None:
    fig, axes = plt.subplots(len(PRODUCTS), 1, figsize=(11, 8), sharex=True)
    for ax, product in zip(axes, PRODUCTS):
        for battery_name, pad_df in pad_level_data.items():
            series = pad_df[pad_df["ProductID"] == product].sort_values("ProductionMonth")
            ax.plot(series["ProductionMonth"], series["Volume"], marker="o", markersize=3, label=battery_name)
        ax.set_ylabel(f"{product} (m3/month)")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("Production month")
    fig.suptitle("Pad-level monthly production: Mahihkan vs Nabiye (2022-01 to 2026-06)")
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


def flag_data_quality(pad_df: pd.DataFrame, battery_name: str) -> list[str]:
    """Flag gaps, large month-over-month step changes, and suspiciously flat runs.

    Heuristic, not authoritative — thresholds are round numbers meant to surface
    candidates for a human look, not a validated statistical test.
    """
    issues = []
    full_range = pd.date_range(pad_df["ProductionMonth"].min(), pad_df["ProductionMonth"].max(), freq="MS")

    for product in PRODUCTS:
        series = pad_df[pad_df["ProductID"] == product].set_index("ProductionMonth")["Volume"].sort_index()
        if series.empty:
            issues.append(f"{product}: no data at all for this battery")
            continue

        missing = full_range.difference(series.index)
        if len(missing) > 0:
            issues.append(f"{product}: {len(missing)} missing month(s) — {list(missing.strftime('%Y-%m'))}")

        pct_change = series.pct_change()
        for month, change in pct_change[pct_change.abs() > STEP_CHANGE_THRESHOLD].dropna().items():
            issues.append(f"{product}: step change at {month:%Y-%m} ({change:+.0%} vs prior month)")

        rolling_std = series.rolling(FLAT_WINDOW_MONTHS).std()
        flat_ends = rolling_std[(rolling_std < series.mean() * FLAT_STD_FRACTION) & rolling_std.notna()]
        if not flat_ends.empty:
            issues.append(
                f"{product}: flat {FLAT_WINDOW_MONTHS}-month window(s) ending "
                f"{list(flat_ends.index.strftime('%Y-%m'))}"
            )

    return issues


def plot_well_counts(well_level_data: dict[str, pd.DataFrame], outpath: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4))
    for battery_name, well_level in well_level_data.items():
        producers = well_level[(~well_level["IsInjector"]) & (well_level["ProductID"] == "OIL")]
        counts = producers.groupby("ProductionMonth")["FromToID"].nunique().sort_index()
        ax.plot(counts.index, counts.values, marker="o", markersize=3, label=battery_name)
    ax.set_ylabel("Distinct producing wells reporting OIL")
    ax.set_xlabel("Production month")
    ax.set_title("Producing well count per month")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(outpath, dpi=120)
    plt.close(fig)


def summary_stats(pad_df: pd.DataFrame, battery_name: str) -> dict:
    oil = pad_df[pad_df["ProductID"] == "OIL"].sort_values("ProductionMonth")
    full_range = pd.date_range(pad_df["ProductionMonth"].min(), pad_df["ProductionMonth"].max(), freq="MS")
    return {
        "battery": battery_name,
        "first_month": oil["ProductionMonth"].min().strftime("%Y-%m"),
        "last_month": oil["ProductionMonth"].max().strftime("%Y-%m"),
        "months_expected": len(full_range),
        "months_with_oil_data": oil["ProductionMonth"].nunique(),
        "completeness_pct": round(100 * oil["ProductionMonth"].nunique() / len(full_range), 1),
        "oil_min_m3": round(oil["Volume"].min(), 1),
        "oil_max_m3": round(oil["Volume"].max(), 1),
        "oil_mean_m3": round(oil["Volume"].mean(), 1),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_lines = []

    well_level_data = {name: load_well_level(name) for name in TARGET_BATTERIES.values()}
    pad_level_data = {name: load_pad_level(name) for name in TARGET_BATTERIES.values()}

    for name, pad_df in pad_level_data.items():
        unexpected = set(pad_df["ProductID"].unique()) - set(PRODUCTS)
        if unexpected:
            print(f"NOTE: {name} has ProductID(s) not covered by this script's plots: {unexpected}")

    # 1. individual well sawtooth plots
    for name, well_level in well_level_data.items():
        wells = pick_sample_wells(well_level)
        outpath = OUTPUT_DIR / f"{battery_slug(name)}_well_sawtooth.png"
        plot_well_sawtooth(well_level, wells, name, outpath)
        print(f"Saved {outpath}")

    # 2. pad-level comparison, same time axis
    outpath = OUTPUT_DIR / "pad_level_comparison.png"
    plot_pad_level_comparison(pad_level_data, outpath)
    print(f"Saved {outpath}")

    # 3. data quality flags
    report_lines.append("=== Data quality flags ===")
    for name, pad_df in pad_level_data.items():
        issues = flag_data_quality(pad_df, name)
        report_lines.append(f"--- {name} ---")
        if issues:
            report_lines.extend(f"  {issue}" for issue in issues)
        else:
            report_lines.append("  (none found)")
        report_lines.append("")

    # 4. producing well count per month
    outpath = OUTPUT_DIR / "producing_well_count.png"
    plot_well_counts(well_level_data, outpath)
    print(f"Saved {outpath}")

    # 5. summary stats
    report_lines.append("=== Summary stats ===")
    for name, pad_df in pad_level_data.items():
        report_lines.append(str(summary_stats(pad_df, name)))

    report_text = "\n".join(report_lines)
    print()
    print(report_text)
    (OUTPUT_DIR / "report.txt").write_text(report_text, encoding="utf-8")


if __name__ == "__main__":
    main()
