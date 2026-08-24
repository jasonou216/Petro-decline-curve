"""Phase 4: within-well and cross-sectional cycle-degradation comparison.

Uses only the 1,875 high-confidence fits from decline_fits_full.csv —
low-confidence cycles stay in that file untouched, just excluded here.
Computes per-cycle EUR (petro_decline.eur.cycle_eur) and compares
qi/Di/b/EUR two ways:

  1. Within-well trajectory (primary): each well's own high-confidence
     cycles, re-ranked chronologically among just its HC cycles (1st HC
     cycle, 2nd HC cycle, ...) — NOT the same as the raw cycle_number, since
     a well can have a low-confidence cycle sitting between two HC ones.
     Compared 1st->2nd (555 wells) and 2nd->3rd (subset of those 134 wells
     reaching a 3rd HC cycle).
  2. Cross-sectional (secondary): all cycles at raw cycle_number==1 pooled
     vs. all cycles at cycle_number>=3 pooled, regardless of well — this
     *does* use the raw position (not the HC-only re-rank), matching how the
     1st/2nd/3rd+ coverage check was already framed and reported.

Both broken out by battery. Plain tables only — no dashboard, no plots —
per instruction to see the pattern before deciding how it gets presented.

Run with: python notebooks/cycle_degradation_comparison.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from petro_decline.eur import cycle_eur  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"

MIN_WELLS_FOR_PCT = 10  # below this, report raw up/down counts instead of a % — too small to be meaningful
METRICS = ["qi", "Di", "b", "EUR"]


def _direction(before: float, after: float) -> str:
    """'up' / 'down' / 'flat' — ties must not silently default to 'down'."""
    if after > before:
        return "up"
    if after < before:
        return "down"
    return "flat"


def load_high_confidence_fits() -> pd.DataFrame:
    fits = pd.read_csv(OUTPUT_DIR / "decline_fits_full.csv")
    hc = fits[~fits["low_confidence"]].copy()
    hc["EUR"] = hc.apply(
        lambda row: cycle_eur(row["model"], row["qi"], row["Di"], row["b"], row["duration_months"]), axis=1
    )
    hc = hc.sort_values(["Battery", "FromToID", "cycle_start"])
    hc["hc_sequence"] = hc.groupby(["Battery", "FromToID"]).cumcount() + 1
    return hc


# --- Within-well trajectory -------------------------------------------------


def within_well_transition(hc: pd.DataFrame, from_seq: int, to_seq: int) -> pd.DataFrame:
    """One row per well with both hc_sequence==from_seq and ==to_seq, with directions."""
    a = hc[hc["hc_sequence"] == from_seq].set_index(["Battery", "FromToID"])
    b = hc[hc["hc_sequence"] == to_seq].set_index(["Battery", "FromToID"])
    common = a.index.intersection(b.index)
    a, b = a.loc[common], b.loc[common]

    result = pd.DataFrame(index=common)
    for metric in METRICS:
        result[f"{metric}_from"] = a[metric]
        result[f"{metric}_to"] = b[metric]
        result[f"{metric}_direction"] = [_direction(before, after) for before, after in zip(a[metric], b[metric])]
    return result.reset_index()


def direction_line(transitions: pd.DataFrame, metric: str) -> str:
    n = len(transitions)
    if n == 0:
        return f"    {metric}: no wells with this transition"
    counts = transitions[f"{metric}_direction"].value_counts()
    up, down, flat = counts.get("up", 0), counts.get("down", 0), counts.get("flat", 0)
    flat_note = f", {flat} flat" if flat else ""
    if n < MIN_WELLS_FOR_PCT:
        return f"    {metric}: {up} up / {down} down{flat_note} of {n} wells (n too small for % to be meaningful)"
    return f"    {metric}: {up} up ({100 * up / n:.1f}%) / {down} down ({100 * down / n:.1f}%){flat_note} of {n} wells"


def report_within_well(hc: pd.DataFrame, label: str) -> list[str]:
    lines = [f"--- Within-well trajectory: {label} ---"]

    t12 = within_well_transition(hc, 1, 2)
    lines.append(f"  1st HC cycle -> 2nd HC cycle ({len(t12)} wells):")
    lines.extend(direction_line(t12, m) for m in METRICS)

    t23 = within_well_transition(hc, 2, 3)
    lines.append(f"  2nd HC cycle -> 3rd HC cycle ({len(t23)} wells):")
    lines.extend(direction_line(t23, m) for m in METRICS)

    three_plus = hc[hc["hc_sequence"] <= 3].groupby(["Battery", "FromToID"])["hc_sequence"].max()
    three_plus_wells = three_plus[three_plus == 3].index
    if len(three_plus_wells) > 0:
        pivot = hc[hc["hc_sequence"] <= 3].set_index(["Battery", "FromToID", "hc_sequence"])
        lines.append(f"  3-point monotonic trend classification ({len(three_plus_wells)} wells with 3+ HC cycles):")
        for metric in METRICS:
            series = pivot[metric].unstack("hc_sequence").loc[three_plus_wells]
            increasing = ((series[2] > series[1]) & (series[3] > series[2])).sum()
            decreasing = ((series[2] < series[1]) & (series[3] < series[2])).sum()
            mixed = len(series) - increasing - decreasing
            lines.append(
                f"    {metric}: {increasing} monotonic-increasing, {decreasing} monotonic-decreasing, "
                f"{mixed} mixed/non-monotonic (of {len(series)})"
            )

    return lines


# --- Cross-sectional ---------------------------------------------------------


def report_cross_sectional(hc: pd.DataFrame, label: str) -> list[str]:
    lines = [f"--- Cross-sectional: {label} ---"]
    first = hc[hc["cycle_number"] == 1]
    third_plus = hc[hc["cycle_number"] >= 3]
    lines.append(f"  1st-position: n={len(first)}, 3rd+-position: n={len(third_plus)}")

    for metric in METRICS:
        med_first = first[metric].median()
        med_third = third_plus[metric].median()
        direction = _direction(med_first, med_third)
        lines.append(
            f"    {metric}: median 1st={med_first:.4g}, median 3rd+={med_third:.4g} ({direction} from 1st to 3rd+)"
        )
    return lines


# --- Agreement check ----------------------------------------------------------


def report_agreement(hc: pd.DataFrame, label: str) -> list[str]:
    lines = [f"--- Agreement check: {label} ---"]
    t12 = within_well_transition(hc, 1, 2)
    first = hc[hc["cycle_number"] == 1]
    third_plus = hc[hc["cycle_number"] >= 3]

    for metric in METRICS:
        if len(t12) == 0:
            lines.append(f"    {metric}: no within-well data to compare")
            continue
        within_up = (t12[f"{metric}_direction"] == "up").sum()
        within_down = (t12[f"{metric}_direction"] == "down").sum()
        within_direction = _direction(within_down, within_up)

        cross_direction = _direction(first[metric].median(), third_plus[metric].median())

        if within_direction == "flat" or cross_direction == "flat":
            flag = "FLAT/INCONCLUSIVE"
        elif within_direction == cross_direction:
            flag = "AGREE"
        else:
            flag = "DIVERGE"
        lines.append(
            f"    {metric}: within-well majority={within_direction} ({within_up}up/{within_down}down), "
            f"cross-sectional={cross_direction} -> {flag}"
        )
    return lines


def main() -> None:
    hc = load_high_confidence_fits()
    hc.to_csv(OUTPUT_DIR / "high_confidence_cycles_with_eur.csv", index=False)

    report_lines = []
    for battery_name, battery_hc in [("Combined", hc), *hc.groupby("Battery")]:
        report_lines.append(f"\n{'=' * 70}\n{battery_name} (n={len(battery_hc)} high-confidence cycles)\n{'=' * 70}")
        report_lines.extend(report_within_well(battery_hc, battery_name))
        report_lines.append("")
        report_lines.extend(report_cross_sectional(battery_hc, battery_name))
        report_lines.append("")
        report_lines.extend(report_agreement(battery_hc, battery_name))

    report_text = "\n".join(report_lines)
    print(report_text)
    (OUTPUT_DIR / "cycle_degradation_comparison.txt").write_text(report_text, encoding="utf-8")


if __name__ == "__main__":
    main()
