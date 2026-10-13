"""Robustness checks on the cycle-over-cycle finding.

1. Detection settings: rerun detection and fitting with a wider minimum
   spacing and with a required steam gap, and see what changes (cycle counts,
   cycle lengths, how many fits are trusted, and whether qi and per-cycle
   recovery still fall from a well's 1st to its 2nd high-confidence cycle).
2. Well groups: the same finding for subsets of the committed pipeline output
   (sidetracks excluded, wells that started inside the data window only, each
   battery alone).

Run with: python notebooks/sensitivity_checks.py
Needs notebooks/detect_cycles_full.py to have run (reads well_profiles.csv).
Writes notebooks/output/sensitivity_report.txt.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from explore_cycle_detection import load_well_level  # noqa: E402
from petro_decline import decline  # noqa: E402
from petro_decline.cycles import DetectionSettings, detect_cycles  # noqa: E402
from petro_decline.data import TARGET_BATTERIES, well_oil_series  # noqa: E402
from petro_decline.eur import cycle_eur  # noqa: E402
from petro_decline.outages import fill_outages, find_outage_months, mask_outages  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

SETTINGS = {
    "baseline (spacing 4, no gap rule)": DetectionSettings(),
    "spacing 8": DetectionSettings(min_spacing_months=8),
    "spacing 12": DetectionSettings(min_spacing_months=12),
    "steam gap <= 25% of peak": DetectionSettings(steam_gap_max_fraction=0.25),
    "steam gap <= 10% of peak": DetectionSettings(steam_gap_max_fraction=0.10),
}


def load_series(profiles: pd.DataFrame) -> dict[str, dict[str, tuple[pd.Series, pd.Series]]]:
    """{battery: {well: (series for detection, series for fitting)}} for eligible wells."""
    eligible = profiles[profiles["excluded_reason"].fillna("") == ""]
    series: dict[str, dict] = {}
    for battery, group in eligible.groupby("Battery"):
        well_level = load_well_level(battery)
        outages = find_outage_months(well_level)
        series[battery] = {}
        for well_id in group["FromToID"]:
            raw = well_oil_series(well_level, well_id)
            series[battery][well_id] = (fill_outages(raw, outages), mask_outages(raw, outages))
    return series


def cycles_for(series: dict, settings: DetectionSettings) -> pd.DataFrame:
    rows = []
    for battery, wells in series.items():
        for well_id, (detect_series, _) in wells.items():
            for cycle in detect_cycles(detect_series, settings)["cycles"]:
                rows.append({"Battery": battery, "FromToID": well_id, **cycle})
    return pd.DataFrame(rows)


def add_eur(fits: pd.DataFrame) -> pd.DataFrame:
    """High-confidence fits with EUR and their within-well order."""
    hc = fits[~fits["low_confidence"]].copy()
    hc["EUR"] = [cycle_eur(r.model, r.qi, r.Di, r.b, r.duration_months) for r in hc.itertuples()]
    hc = hc.sort_values(["Battery", "FromToID", "cycle_start"])
    hc["hc_sequence"] = hc.groupby(["Battery", "FromToID"]).cumcount() + 1
    return hc


def first_to_second(hc: pd.DataFrame) -> dict:
    """Share of wells where qi and EUR fall from the 1st to the 2nd high-confidence cycle."""
    first = hc[hc["hc_sequence"] == 1].set_index(["Battery", "FromToID"])
    second = hc[hc["hc_sequence"] == 2].set_index(["Battery", "FromToID"])
    common = first.index.intersection(second.index)
    if len(common) == 0:
        return {"wells": 0, "qi_down": float("nan"), "eur_down": float("nan")}
    return {
        "wells": len(common),
        "qi_down": float((second.loc[common, "qi"] < first.loc[common, "qi"]).mean()),
        "eur_down": float((second.loc[common, "EUR"] < first.loc[common, "EUR"]).mean()),
    }


def summarize_setting(label: str, group: str, cycles: pd.DataFrame, fits: pd.DataFrame, hc: pd.DataFrame) -> dict:
    complete = cycles[(~cycles["is_final_cycle"]) & (~cycles["is_startup_ramp"])]
    return {
        "setting": label,
        "group": group,
        "fittable cycles": len(fits),
        "median length (mo)": float(complete["duration_months"].median()),
        "cycles >= 24 mo": float((complete["duration_months"] >= 24).mean()),
        "high confidence": float((~fits["low_confidence"]).mean()),
        "HC cycles": len(hc),
        **{f"1->2 {k}": v for k, v in first_to_second(hc).items()},
    }


def run_setting(label: str, settings: DetectionSettings, series: dict) -> list[dict]:
    """One summary row for all wells, then one per battery."""
    cycles = cycles_for(series, settings)
    fit_series = {b: {w: s[1] for w, s in wells.items()} for b, wells in series.items()}
    fits = decline.fit_all_cycles(cycles, fit_series)
    hc = add_eur(fits)

    rows = [summarize_setting(label, "both", cycles, fits, hc)]
    for battery in series:
        rows.append(
            summarize_setting(
                label,
                battery.split()[0],
                cycles[cycles["Battery"] == battery],
                fits[fits["Battery"] == battery],
                hc[hc["Battery"] == battery],
            )
        )
    return rows


def detection_sensitivity(profiles: pd.DataFrame) -> pd.DataFrame:
    series = load_series(profiles)
    rows = []
    for label, settings in SETTINGS.items():
        print(f"running: {label}")
        rows.extend(run_setting(label, settings, series))
    return pd.DataFrame(rows)


def group_checks(profiles: pd.DataFrame) -> pd.DataFrame:
    """The 1st->2nd high-confidence finding for subsets of the committed pipeline output."""
    hc = pd.read_csv(OUTPUT_DIR / "high_confidence_cycles_with_eur.csv")
    hc = hc.merge(profiles[["Battery", "FromToID", "new_in_window", "is_redrill"]], on=["Battery", "FromToID"], how="left")
    groups = {
        "all wells": hc,
        "excluding sidetracks / redrills": hc[~hc["is_redrill"]],
        "wells that started in the window": hc[hc["new_in_window"]],
        "wells already producing at window start": hc[~hc["new_in_window"]],
        "Mahihkan only": hc[hc["Battery"] == "Mahihkan Battery 02-21"],
        "Nabiye only": hc[hc["Battery"] == "Nabiye 11-23"],
    }
    rows = []
    for label, group in groups.items():
        rows.append({"group": label, "HC cycles": len(group), **first_to_second(group)})
    return pd.DataFrame(rows)


def fmt(df: pd.DataFrame) -> str:
    pct = [c for c in df.columns if c in ("cycles >= 24 mo", "high confidence", "1->2 qi_down", "1->2 eur_down", "qi_down", "eur_down")]
    out = df.copy()
    for col in pct:
        out[col] = out[col].map(lambda v: f"{v:.0%}" if pd.notna(v) else "n/a")
    if "median length (mo)" in out:
        out["median length (mo)"] = out["median length (mo)"].round(1)
    return out.to_string(index=False)


def main() -> None:
    profiles = pd.read_csv(OUTPUT_DIR / "well_profiles.csv", parse_dates=["first_reported"])
    lines = ["=== Detection settings (same eligible wells, outage months masked) ===", fmt(detection_sensitivity(profiles))]
    lines += ["", "=== 1st -> 2nd high-confidence cycle by well group (committed pipeline output) ===", fmt(group_checks(profiles))]
    report = "\n".join(lines)
    print()
    print(report)
    (OUTPUT_DIR / "sensitivity_report.txt").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
