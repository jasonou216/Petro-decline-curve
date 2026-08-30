"""Cold Lake CSS decline-curve dashboard (Streamlit).

Panels 1-3: a Dashboard tab (battery-overview landing page, two-column
well-detail view once a well is picked, per-cycle table in an expander)
and a Glossary tab. Colors follow the dataviz skill's validated dark-mode
palette (references/palette.md): status green/amber for confidence,
categorical blue/orange to distinguish the two batteries everywhere.

Every domain term gets two levels of explanation: a one-line phrase via
Streamlit's native `help=` tooltip (selectboxes, metric tiles, table
column headers) for someone skimming, and a fuller 1-2 sentence entry in
the Glossary tab for someone who wants it spelled out. GLOSSARY below is
the single source for both — see `glossary_help()`.

Reads already-computed CSVs from notebooks/output/ and data/processed/ and
does not re-run cycle detection or re-fit anything. The only "live"
computation here is evaluating already-fitted Arps curves
(petro_decline.decline.predict) to draw them, which is visualization, not
re-fitting.

Run with: streamlit run app.py
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from petro_decline import decline, economics  # noqa: E402
from petro_decline.data import well_oil_series  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "notebooks" / "output"
PROCESSED_DIR = Path(__file__).resolve().parent / "data" / "processed"

# Dark-mode palette, custom (see conversation notes: chosen to avoid both generic
# Tailwind-default hues and Anthropic-brand colors). WCAG-contrast-checked against
# the dark surface below and pairwise RGB-distance-checked for separation; the
# dataviz skill's own CVD-simulation validator needs `node`, which isn't available
# in this environment, so treat the separation check as a rough proxy, not the
# full six-checks validation.
COLOR_SURFACE = "#1a1a19"
COLOR_PAGE = "#0d0d0d"
COLOR_TEXT_PRIMARY = "#ffffff"
COLOR_TEXT_SECONDARY = "#c3c2b7"
COLOR_TEXT_MUTED = "#898781"
COLOR_BORDER = "rgba(255,255,255,0.10)"

# Metric-type accents: one hue per metric category, reused consistently for
# that metric wherever it appears (battery overview and, later, well-detail).
ACCENT_TEAL = "#3FA8A0"  # count-type metrics (total wells, cycle counts)
ACCENT_ROSE = "#C97B86"  # ratio/average-type metrics
ACCENT_SAGE = "#7E9B6E"  # value/EUR-type metrics; doubles as confidence-good status
ACCENT_AMBER = "#DDB13E"  # negative-NPV metric; doubles as confidence-low/warning status

COLOR_GOOD = ACCENT_SAGE  # status: high-confidence
COLOR_WARNING = ACCENT_AMBER  # status: low-confidence
COLOR_CRITICAL = "#C24040"  # status: cycle boundary line / negative indicator
BATTERY_COLORS = {"Mahihkan Battery 02-21": "#6478BD", "Nabiye 11-23": "#C17A4A"}
STARTUP_RAMP_COLOR = "#A176C9"

NO_WELL_SENTINEL = "(Battery overview, no well selected)"

SORT_OPTIONS = {
    "EUR (descending)": ("total_EUR", False),
    "Cycle count (descending)": ("n_cycles", False),
    "NPV (descending)": ("total_NPV", False),
}

# Single source for every domain-term explanation used in this app: a short
# tooltip phrase (for help= parameters) and a fuller plain-language sentence
# (for the Glossary tab). Keep "short" to a phrase, "full" to 1-2 sentences.
GLOSSARY = {
    "CSS (Cyclic Steam Stimulation)": {
        "short": "The steam-soak-produce process used at Cold Lake.",
        "full": "The thermal recovery process used at Cold Lake: steam is injected into a well, left to "
        "soak and heat the bitumen, then the well is switched over to production. This repeats over and "
        "over as the well ages. It's a standard, industry-wide thermal recovery method for Cold Lake "
        "bitumen, not something specific to this dashboard.",
    },
    "Cycle": {
        "short": "One steam-stimulation-to-next-stimulation period.",
        "full": "One full round of steam injection followed by production, starting at a fresh production "
        "spike right after steaming and ending when the well is re-steamed again (or the data runs out). "
        "Detected from the well's own production history by finding each new spike that rises enough "
        "above its recent low point to count as a real re-stimulation rather than noise.",
    },
    "Startup ramp": {
        "short": "A well's first stretch of production, before its first re-stimulation.",
        "full": "The very first stretch of a well's life, before it has ever been re-steamed. Not counted "
        "as a cycle, since a cycle means a *repeat* of the steam-then-produce pattern, and this is the "
        "well's first time producing at all.",
    },
    "Decline curve": {
        "short": "A mathematical curve fit to a cycle's production data.",
        "full": "A mathematical curve fit to a single cycle's production data, showing how output slows "
        "down over time. Fit using the Arps equations below.",
    },
    "Arps model": {
        "short": "The standard equation family for oil and gas decline curves.",
        "full": "The standard equation family used for decline curves (Arps, 1945). General form:\n\n"
        "$$q(t) = \\dfrac{q_i}{(1 + b D_i t)^{1/b}}$$\n\n"
        "This dashboard fits all three shapes below to every cycle and keeps whichever one fits best.",
    },
    "Exponential": {
        "short": "Decline at a constant percentage rate.",
        "full": "Arps decline with b = 0, the fastest-dropping of the three shapes: production falls by "
        "the same percentage every month.\n\n"
        "$$q(t) = q_i\\, e^{-D_i t}$$",
    },
    "Harmonic": {
        "short": "Decline that flattens out slowly over time (though not always the slowest of all fits).",
        "full": "Arps decline with b = 1: it declines more slowly than exponential (b = 0), and slower "
        "than most hyperbolic fits too, though a hyperbolic fit with b > 1 can flatten out even more "
        "than harmonic.\n\n"
        "$$q(t) = \\dfrac{q_i}{1 + D_i t}$$",
    },
    "Hyperbolic": {
        "short": "Decline that gradually flattens, between exponential and harmonic.",
        "full": "Arps decline with b strictly between 0 and 2, excluding b = 0 and b = 1 (which are fit "
        "as their own exponential and harmonic cases). The general Arps equation above, and the most "
        "flexible of the three shapes.",
    },
    "qi": {
        "short": "Initial production rate (m3/month).",
        "full": "The production rate right at the start of a cycle, before decline kicks in (m3/month). "
        "Solved for directly when fitting the Arps equation to the data, not fixed to the observed peak "
        "value.",
    },
    "Di": {
        "short": "Initial decline rate (fraction per month).",
        "full": "The decline rate: how fast production drops off. A bigger number means faster decline. "
        "Solved for when fitting the Arps equation, same as qi.",
    },
    "b": {
        "short": "Decline curve shape parameter (0 to 2).",
        "full": "The shape parameter that decides which Arps curve you're looking at: b = 0 is "
        "exponential, b = 1 is harmonic, anything else is hyperbolic. Solved for when fitting, bounded "
        "between 0 and 2 in this dashboard.",
    },
    "R2": {
        "short": "Goodness of fit (0 to 1, higher is better).",
        "full": "How well the fitted curve matches the real data, from 0 (no fit at all) to 1 (perfect "
        "fit). The standard coefficient-of-determination calculation, comparing the fitted curve's "
        "predicted monthly production against what the well actually produced.",
    },
    "Confidence": {
        "short": "Whether a cycle's fit is trustworthy enough to use.",
        "full": "Whether a cycle's fit is trustworthy. A cycle is flagged low confidence if it's too "
        "short, has a poor R2, or its fit parameters hit unreasonable bounds (an implausibly high Di, or "
        "b pinned right at 0 or 2). Low-confidence cycles are left out of EUR and NPV entirely, rather "
        "than reported with a misleading number.",
    },
    "EUR": {
        "short": "Estimated total oil this cycle will produce (m3).",
        "full": "Estimated Ultimate Recovery: the total oil a cycle is expected to produce, found by "
        "integrating the fitted curve over the cycle's own observed length — not out to an economic "
        "limit, since that would need cost and price assumptions this part of the dashboard doesn't use:\n\n"
        "$$EUR = \\int_0^{T} q(t)\\, dt$$\n\n"
        "where T is the cycle's duration in months.",
    },
    "NPV": {
        "short": "Present-day dollar value of a cycle (USD).",
        "full": "Net Present Value: what a cycle's oil is worth today, after subtracting operating costs "
        "and the steam job's cost, and discounting future months back to present value:\n\n"
        "$$NPV = \\sum_{t=0}^{T-1} \\dfrac{q_t \\times (\\text{price} - \\text{opex})}{(1 + r)^t} - "
        "\\text{steam cost}$$\n\n"
        "r is the monthly discount rate (derived from the annual discount rate below); the steam cost "
        "is incurred in the cycle's first month, t = 0.",
    },
    "IRR": {
        "short": "Annual return rate where costs and revenue break even.",
        "full": "Internal Rate of Return: the discount rate r that would make a cycle's NPV exactly zero. "
        "Solved numerically from the same cash flow used for NPV. A higher IRR relative to the actual "
        "discount rate means a more attractive cycle.",
    },
    "Opex": {
        "short": "Operating cost per barrel of oil produced.",
        "full": "Ongoing operating cost per barrel of oil produced. Set as a dashboard assumption (see "
        "config.yaml), not derived from the data.",
    },
    "Steam cost": {
        "short": "One-time cost of a re-stimulation job.",
        "full": "The one-time cost of a re-stimulation job. Set as a dashboard assumption (see "
        "config.yaml), not derived from the data, since steam volumes aren't part of this dataset.",
    },
    "Discount rate": {
        "short": "Rate used to convert future dollars to today's value.",
        "full": "The rate used to shrink future dollars down to today's value in the NPV calculation, "
        "reflecting that a dollar next year is worth less than a dollar today. Set as a dashboard "
        "assumption (see config.yaml), following standard oil and gas project evaluation convention.",
    },
    "WTI": {
        "short": "Benchmark North American oil price (USD/bbl).",
        "full": "West Texas Intermediate: the main North American benchmark oil price. Pulled live from "
        "the U.S. Energy Information Administration's public API; if that call fails, this dashboard "
        "falls back to a dated assumption in config.yaml instead of breaking.",
    },
    "WCS": {
        "short": "Actual price received for Alberta heavy oil (USD/bbl).",
        "full": "Western Canadian Select: the benchmark price for the heavier, cheaper Canadian oil "
        "actually produced here. In this dashboard it always trades below WTI by construction, "
        "calculated as WTI minus the WCS differential rather than fetched live:\n\n"
        "$$WCS = WTI - \\text{differential}$$",
    },
    "WCS differential": {
        "short": "Dollar gap between WTI and WCS.",
        "full": "The dollar-per-barrel gap between WTI and WCS. Set as a dashboard assumption based on a "
        "typical historical spread (see config.yaml for the exact source and date).",
    },
    "Battery median": {
        "short": "The typical value across all wells in a battery, at the same cycle number.",
        "full": "The middle value of qi, EUR, or NPV across every well in a battery, compared at the same "
        "position in each well's own cycle history (every well's 1st high-confidence cycle, every well's "
        "2nd, and so on). Used as a reference line to see whether a specific well is typical for its "
        "battery at that point in its life, or notably higher or lower.",
    },
}


def glossary_help(term: str) -> str:
    """Short tooltip phrase for a glossary term, for help= parameters."""
    return GLOSSARY[term]["short"]


def battery_slug(name: str) -> str:
    return name.lower().replace(" ", "_")


# --- Styling ------------------------------------------------------------------


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {COLOR_PAGE}; }}
        .section-header {{
            font-size: 1.05rem; font-weight: 600; color: {COLOR_TEXT_PRIMARY};
            margin: 0.4rem 0 0.6rem 0; padding-bottom: 0.35rem; border-bottom: 1px solid {COLOR_BORDER};
        }}
        .battery-tag {{
            display: inline-block; padding: 2px 10px; border-radius: 999px;
            font-size: 0.8rem; font-weight: 600; margin-bottom: 0.6rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_tile(
    label: str,
    value: str,
    help_text: str = "",
    sublabel: str = "",
    accent_color: str | None = None,
    key: str | None = None,
) -> None:
    """A bordered metric card using native st.metric (so help= renders as a real tooltip).

    accent_color + key together add a colored left border via a CSS rule
    targeting the container's key-derived class (st-key-<key>, a stable
    Streamlit feature since 1.34) — st.metric itself has no per-instance
    styling hook, so this is the only way to get a per-card accent without
    giving up the native tooltip. Omit accent_color/key for a plain card.
    """
    with st.container(border=True, key=key):
        st.metric(label, value, help=help_text or None)
        if sublabel:
            st.caption(sublabel)
    if accent_color and key:
        st.markdown(
            f"<style>.st-key-{key} {{ border-left: 4px solid {accent_color} !important; }}</style>",
            unsafe_allow_html=True,
        )


def section_header(text: str) -> None:
    st.markdown(f'<div class="section-header">{text}</div>', unsafe_allow_html=True)


# --- Cached data loading -----------------------------------------------------


@st.cache_data
def load_cycles() -> pd.DataFrame:
    df = pd.read_csv(OUTPUT_DIR / "cycles_full.csv")
    df["start"] = pd.to_datetime(df["start"])
    df["end"] = pd.to_datetime(df["end"])
    return df


@st.cache_data
def load_fits() -> pd.DataFrame:
    df = pd.read_csv(OUTPUT_DIR / "decline_fits_full.csv")
    df["cycle_start"] = pd.to_datetime(df["cycle_start"])
    return df


@st.cache_data
def load_economics() -> pd.DataFrame:
    df = pd.read_csv(OUTPUT_DIR / "decline_economics_full.csv")
    df["cycle_start"] = pd.to_datetime(df["cycle_start"])
    return df


@st.cache_data
def load_well_summary() -> pd.DataFrame:
    return pd.read_csv(OUTPUT_DIR / "well_economics_summary.csv")


@st.cache_data
def battery_median_by_position(battery: str) -> pd.DataFrame:
    """Median qi/EUR/NPV across every well in `battery`, grouped by hc_sequence
    (each well's 1st high-confidence cycle, 2nd, etc.) — the reference line for
    the per-well degradation panel. Aggregation over already-fitted/already-priced
    values, not a re-fit or a re-run of the economics.
    """
    econ = load_economics()
    battery_econ = econ[econ["Battery"] == battery]
    return battery_econ.groupby("hc_sequence")[["qi", "EUR", "NPV"]].median().reset_index()


@st.cache_data(ttl=3600)
def load_default_assumptions() -> economics.EconomicAssumptions:
    """Live WTI (falls back to config.yaml if the EIA call fails) + everything
    else from config.yaml — cached for an hour so every widget interaction on
    this page doesn't re-hit the EIA API.
    """
    return economics.load_assumptions()


@st.cache_data
def recompute_well_economics(battery: str, well_id: str, wti_price: float, discount_rate_pct: float) -> pd.DataFrame:
    """NPV/IRR/payback for this well's high-confidence cycles at a custom WTI
    price and discount rate — everything else (opex, steam cost, WCS
    differential) held at the dashboard's live/config defaults. Reuses
    `economics.compute_cycle_economics` directly; does not reimplement the
    NPV formula.
    """
    base = load_default_assumptions()
    econ = load_economics()
    well_cycles = econ[(econ["Battery"] == battery) & (econ["FromToID"] == well_id)][
        ["Battery", "FromToID", "cycle_number", "cycle_start", "duration_months", "model", "qi", "Di", "b"]
    ].copy()

    custom_wti = dataclasses.replace(base.wti_price, value=wti_price, source="what-if slider")
    custom_rate = dataclasses.replace(base.discount_rate, value=discount_rate_pct / 100, source="what-if slider")
    custom_assumptions = dataclasses.replace(base, wti_price=custom_wti, discount_rate=custom_rate)

    return economics.compute_cycle_economics(well_cycles, custom_assumptions)


@st.cache_data
def load_well_level(battery_name: str) -> pd.DataFrame:
    df = pd.read_csv(PROCESSED_DIR / f"{battery_slug(battery_name)}_well_level.csv")
    df["ProductionMonth"] = pd.to_datetime(df["ProductionMonth"])
    return df


@st.cache_data
def load_well_oil_series(battery_name: str, well_id: str) -> pd.Series:
    return well_oil_series(load_well_level(battery_name), well_id)


@st.cache_data
def load_well_list() -> pd.DataFrame:
    """Every well that went through cycle detection, with its HC cycle count
    and total EUR/NPV (0 for wells with no high-confidence cycles at all,
    e.g. startup-ramp-only wells) — the source for both the sidebar picker
    and the battery overview.
    """
    all_wells = load_cycles()[["Battery", "FromToID"]].drop_duplicates()
    summary = load_well_summary()
    merged = all_wells.merge(summary, on=["Battery", "FromToID"], how="left")
    merged["n_cycles"] = merged["n_cycles"].fillna(0).astype(int)
    merged["total_EUR"] = merged["total_EUR"].fillna(0.0)
    merged["total_NPV"] = merged["total_NPV"].fillna(0.0)
    return merged.sort_values(["Battery", "FromToID"]).reset_index(drop=True)


# --- Sidebar: battery + sort/filter + well selector --------------------------


def render_sidebar() -> tuple[str, str | None]:
    well_list = load_well_list()

    st.sidebar.header("Well selector")
    battery = st.sidebar.selectbox(
        "Battery", sorted(well_list["Battery"].unique()), help="Choose which Cold Lake battery to browse wells from."
    )

    sort_label = st.sidebar.selectbox(
        "Sort wells by", list(SORT_OPTIONS.keys()), help="Order the well list below, highest first."
    )
    sort_col, ascending = SORT_OPTIONS[sort_label]

    only_multi_cycle = st.sidebar.checkbox(
        "Only wells with 2+ cycles",
        value=False,
        help="Show only wells with enough high-confidence cycles to compare cycle-over-cycle degradation.",
    )

    battery_wells = well_list[well_list["Battery"] == battery].copy()
    if only_multi_cycle:
        battery_wells = battery_wells[battery_wells["n_cycles"] >= 2]
    battery_wells = battery_wells.sort_values(sort_col, ascending=ascending).reset_index(drop=True)

    def format_label(row: pd.Series) -> str:
        cycle_word = "cycle" if row["n_cycles"] == 1 else "cycles"
        return f"{row['FromToID']} ({row['n_cycles']} {cycle_word}, EUR {row['total_EUR']:,.0f} m3)"

    battery_wells["label"] = battery_wells.apply(format_label, axis=1)
    options = [NO_WELL_SENTINEL, *battery_wells["label"].tolist()]
    choice = st.sidebar.selectbox(
        "Well", options, index=0, help="Pick a well to see its production history and per-cycle detail."
    )

    if choice == NO_WELL_SENTINEL:
        return battery, None
    well_id = battery_wells.loc[battery_wells["label"] == choice, "FromToID"].iloc[0]
    return battery, well_id


# --- Battery overview (landing view) -----------------------------------------


def render_intro() -> None:
    # A bordered neutral card, not st.info() — st.info's blue fill is exactly the
    # "generic AI dashboard" look this pass is removing; a plain border on the
    # same dark surface as everything else reads as part of the page, not a banner.
    with st.container(border=True):
        st.markdown(
            "**What you're looking at:** real production data from two Cold Lake oil batteries, "
            "Mahihkan and Nabiye. Wells here get re-steamed periodically (called cyclic steam "
            "stimulation, or CSS) to keep the oil flowing.\n\n"
            "**What the curves mean:** every time a well gets re-steamed, production jumps up "
            "then slowly drops off until the next steam job. This dashboard fits a decline curve "
            "to each of those cycles on its own, so you can actually answer things like "
            "\"how much oil is this cycle going to give us in total?\" and \"is it still worth "
            "re-steaming this well?\"\n\n"
            "**How to use it:** pick a battery and a well from the sidebar. You'll see that "
            "well's real production history, the decline curve fitted to each cycle, and what "
            "it means economically.\n\n"
            "Check the **Glossary** tab up top if any of the terms need an explanation."
        )
    st.caption(
        "Data obtained from Petrinex (Alberta's public well-production registry) and the U.S. "
        "Energy Information Administration (WTI oil price)."
    )


def battery_overview_stats(battery: str) -> dict:
    """Battery-level aggregates for the overview cards. All of these are
    aggregations (sum/mean/count) over the already-computed Phase 5 outputs
    (well_economics_summary.csv, decline_economics_full.csv) — nothing here
    re-runs curve fitting or re-prices any cycle.
    """
    well_list = load_well_list()
    battery_wells = well_list[well_list["Battery"] == battery]
    wells_with_cycles = battery_wells[battery_wells["n_cycles"] > 0]

    total_wells = len(battery_wells)
    total_eur = battery_wells["total_EUR"].sum()
    total_cycles = battery_wells["n_cycles"].sum()
    avg_cycles = total_cycles / total_wells if total_wells else 0.0

    n_with_cycles = len(wells_with_cycles)
    n_negative = int((wells_with_cycles["total_NPV"] < 0).sum())
    negative_pct = 100 * n_negative / n_with_cycles if n_with_cycles else 0.0

    total_npv = wells_with_cycles["total_NPV"].sum()

    battery_econ = load_economics()
    battery_econ = battery_econ[battery_econ["Battery"] == battery]
    n_cycles_total = len(battery_econ)
    n_cycles_negative = int((battery_econ["NPV"] < 0).sum())
    pct_cycles_negative = 100 * n_cycles_negative / n_cycles_total if n_cycles_total else 0.0

    return {
        "total_wells": total_wells,
        "total_eur": total_eur,
        "avg_cycles": avg_cycles,
        "negative_pct": negative_pct,
        "n_with_cycles": n_with_cycles,
        "total_npv": total_npv,
        "pct_cycles_negative": pct_cycles_negative,
        "n_cycles_total": n_cycles_total,
    }


def render_battery_card(battery: str) -> None:
    color = BATTERY_COLORS[battery]
    slug = battery_slug(battery)
    st.markdown(
        f'<span class="battery-tag" style="background:{color}22; color:{color};">{battery}</span>',
        unsafe_allow_html=True,
    )
    stats = battery_overview_stats(battery)

    col1, col2 = st.columns(2)
    with col1:
        metric_tile(
            "Total wells analyzed",
            f"{stats['total_wells']:,}",
            accent_color=ACCENT_TEAL,
            key=f"{slug}_wells",
        )
        metric_tile(
            "Avg. high-confidence cycles per well",
            f"{stats['avg_cycles']:.2f}",
            help_text=glossary_help("Cycle"),
            accent_color=ACCENT_ROSE,
            key=f"{slug}_avgcycles",
        )
        metric_tile(
            "Total EUR (high-confidence cycles)",
            f"{stats['total_eur']:,.0f} m3",
            help_text=glossary_help("EUR"),
            accent_color=ACCENT_SAGE,
            key=f"{slug}_eur",
        )
    with col2:
        npv_color = COLOR_CRITICAL if stats["total_npv"] < 0 else STARTUP_RAMP_COLOR
        metric_tile(
            "Total NPV (high-confidence cycles)",
            f"${stats['total_npv']:,.0f}",
            help_text=glossary_help("NPV"),
            accent_color=npv_color,
            key=f"{slug}_totalnpv",
        )
        wells_npv_flag = "\U0001F534" if stats["negative_pct"] > 0 else "\U0001F7E2"
        metric_tile(
            "Wells with negative total NPV",
            f"{wells_npv_flag} {stats['negative_pct']:.1f}%",
            help_text=glossary_help("NPV"),
            sublabel=f"of {stats['n_with_cycles']} wells with at least one high-confidence cycle",
            accent_color=ACCENT_AMBER,
            key=f"{slug}_negnpv",
        )
        cycles_npv_flag = "\U0001F534" if stats["pct_cycles_negative"] > 0 else "\U0001F7E2"
        metric_tile(
            "Cycles with negative NPV",
            f"{cycles_npv_flag} {stats['pct_cycles_negative']:.1f}%",
            help_text=glossary_help("NPV"),
            sublabel=f"of {stats['n_cycles_total']} high-confidence cycles",
            accent_color=ACCENT_AMBER,
            key=f"{slug}_negcycles",
        )


def render_battery_overview() -> None:
    render_intro()
    section_header("Battery overview")
    st.caption("Select a well from the sidebar to see its production history and per-cycle detail.")

    col1, col2 = st.columns(2)
    with col1:
        render_battery_card("Mahihkan Battery 02-21")
    with col2:
        render_battery_card("Nabiye 11-23")


# --- Well detail view ----------------------------------------------------------


def render_production_chart(battery: str, well_id: str) -> None:
    series = load_well_oil_series(battery, well_id)
    well_cycles = load_cycles()
    well_cycles = well_cycles[(well_cycles["Battery"] == battery) & (well_cycles["FromToID"] == well_id)].sort_values("start")
    well_fits = load_fits()
    well_fits = well_fits[(well_fits["Battery"] == battery) & (well_fits["FromToID"] == well_id)].sort_values("cycle_start")

    # cycles_full.csv (well_cycles) has no cycle_number — only fitted cycles do
    # (decline_fits_full.csv). Look it up by cycle_start to label each boundary.
    cycle_number_by_start = dict(zip(well_fits["cycle_start"], well_fits["cycle_number"]))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=series.index, y=series.values, mode="lines+markers", name="OIL (m3/month)", line=dict(color=COLOR_TEXT_SECONDARY))
    )

    for _, row in well_cycles.iterrows():
        is_ramp = bool(row["is_startup_ramp"])
        line_color = STARTUP_RAMP_COLOR if is_ramp else COLOR_CRITICAL
        fig.add_vline(
            x=row["start"].strftime("%Y-%m-%d"),
            line=dict(color=line_color, dash="dot" if is_ramp else "dash", width=1.5),
            opacity=0.7,
        )
        label_text = "ramp" if is_ramp else str(int(cycle_number_by_start.get(row["start"], 0)))
        fig.add_annotation(
            x=row["start"],
            y=1.0,
            yref="paper",
            yanchor="bottom",
            text=label_text,
            showarrow=False,
            font=dict(size=11, color=line_color),
            bgcolor=COLOR_SURFACE,
        )

    for _, row in well_fits.iterrows():
        if pd.isna(row["model"]):
            continue  # no Arps form converged for this cycle — nothing to draw (see Glossary: Confidence)
        t = np.arange(int(row["duration_months"]), dtype=float)
        fitted = decline.predict(t, row["model"], row["qi"], row["Di"], row["b"])
        dates = pd.date_range(row["cycle_start"], periods=int(row["duration_months"]), freq="MS")
        color = COLOR_WARNING if row["low_confidence"] else COLOR_GOOD
        fig.add_trace(go.Scatter(x=dates, y=fitted, mode="lines", line=dict(color=color, width=3), showlegend=False, hoverinfo="skip"))

    fig.update_layout(
        height=440,
        margin=dict(l=10, r=10, t=30, b=10),
        yaxis_title="OIL (m3/month)",
        xaxis_title="Production month",
        paper_bgcolor=COLOR_SURFACE,
        plot_bgcolor=COLOR_SURFACE,
        font=dict(color=COLOR_TEXT_SECONDARY),
        showlegend=False,
    )
    st.plotly_chart(fig, width='stretch')
    st.caption(
        "Startup ramp: dotted violet line, excluded from fitting. Cycle boundary: dashed red line, "
        "numbered to match the per-cycle table below. Fitted curve: green (high confidence) or amber "
        "(low confidence)."
    )


def render_well_summary_cards(battery: str, well_id: str) -> None:
    well_list = load_well_list()
    row = well_list[(well_list["Battery"] == battery) & (well_list["FromToID"] == well_id)].iloc[0]

    metric_tile("High-confidence cycles", f"{row['n_cycles']:,}", help_text=glossary_help("Confidence"))
    metric_tile("Total EUR", f"{row['total_EUR']:,.0f} m3", help_text=glossary_help("EUR"))
    npv_flag = "\U0001F534" if row["total_NPV"] < 0 else "\U0001F7E2"
    metric_tile("Total NPV", f"{npv_flag} ${row['total_NPV']:,.0f}", help_text=glossary_help("NPV"))

    fits = load_fits()
    well_fits = fits[(fits["Battery"] == battery) & (fits["FromToID"] == well_id)]
    if not well_fits.empty:
        hc_rate = 100 * (~well_fits["low_confidence"]).sum() / len(well_fits)
        metric_tile(
            "Cycles rated high confidence",
            f"{hc_rate:.0f}%",
            help_text=glossary_help("Confidence"),
            sublabel=f"of {len(well_fits)} total fitted cycles",
        )


def render_cycle_table(battery: str, well_id: str) -> None:
    well_cycles = load_cycles()
    well_cycles = well_cycles[(well_cycles["Battery"] == battery) & (well_cycles["FromToID"] == well_id)].sort_values("start")
    well_fits = load_fits()
    well_fits = well_fits[(well_fits["Battery"] == battery) & (well_fits["FromToID"] == well_id)]
    # Sorted by cycle_start (chronological), not the stored cycle_number, as a
    # deliberate double-check — verified equivalent across all 1,543 wells in
    # this dataset (see notebooks/ dev notes), but sorting by the actual
    # timestamp rules out that edge case by construction rather than by trust.
    well_fits = well_fits.sort_values("cycle_start")
    econ = load_economics()
    econ = econ[(econ["Battery"] == battery) & (econ["FromToID"] == well_id)][["cycle_number", "EUR", "NPV"]]

    table = well_fits.merge(econ, on="cycle_number", how="left")
    table["confidence"] = table["low_confidence"].map({True: "low", False: "high"})

    display = pd.DataFrame(
        {
            "cycle #": table["cycle_number"].astype(str),
            "model": table["model"],
            "qi": table["qi"].map(lambda v: f"{v:,.1f}" if pd.notna(v) else "(n/a)"),
            "Di": table["Di"].map(lambda v: f"{v:.4f}" if pd.notna(v) else "(n/a)"),
            "b": table["b"].map(lambda v: f"{v:.3f}" if pd.notna(v) else "(n/a)"),
            "R2": table["r_squared"].map(lambda v: f"{v:.3f}" if pd.notna(v) else "(n/a)"),
            "EUR": table["EUR"].map(lambda v: f"{v:,.0f}" if pd.notna(v) else "(n/a)"),
            "NPV": table["NPV"].map(lambda v: f"${v:,.0f}" if pd.notna(v) else "(n/a)"),
            "confidence": table["confidence"],
        }
    )

    ramp = well_cycles[well_cycles["is_startup_ramp"]]
    if not ramp.empty:
        ramp_row = pd.DataFrame(
            [
                {
                    "cycle #": "startup ramp",
                    "model": "(n/a)",
                    "qi": "(n/a)",
                    "Di": "(n/a)",
                    "b": "(n/a)",
                    "R2": "(n/a)",
                    "EUR": "(n/a)",
                    "NPV": "(n/a)",
                    "confidence": "n/a (excluded)",
                }
            ]
        )
        display = pd.concat([ramp_row, display], ignore_index=True)

    st.dataframe(
        display,
        width='stretch',
        hide_index=True,
        column_config={
            "cycle #": st.column_config.TextColumn("cycle #", help="Which cycle this row describes, in chronological order."),
            "model": st.column_config.TextColumn(
                "model", help="Which Arps decline shape fit best: exponential, hyperbolic, or harmonic (see Glossary tab)."
            ),
            "qi": st.column_config.TextColumn("qi", help=glossary_help("qi")),
            "Di": st.column_config.TextColumn("Di", help=glossary_help("Di")),
            "b": st.column_config.TextColumn("b", help=glossary_help("b")),
            "R2": st.column_config.TextColumn("R2", help=glossary_help("R2")),
            "EUR": st.column_config.TextColumn("EUR", help=glossary_help("EUR")),
            "NPV": st.column_config.TextColumn("NPV", help=glossary_help("NPV")),
            "confidence": st.column_config.TextColumn("confidence", help=glossary_help("Confidence")),
        },
    )


# --- Cycle-degradation panel ---------------------------------------------------


def render_degradation_chart(battery: str, well_econ: pd.DataFrame, battery_medians: pd.DataFrame) -> None:
    """Bars: this well's own qi/EUR/NPV per cycle, in chronological (hc_sequence)
    order. Dashed line: the battery median at each of those same positions.
    """
    battery_color = BATTERY_COLORS[battery]
    max_position = int(well_econ["hc_sequence"].max())
    relevant_medians = battery_medians[battery_medians["hc_sequence"] <= max_position]

    fig = make_subplots(rows=1, cols=3, subplot_titles=("qi (m3/month)", "EUR (m3)", "NPV (USD)"))

    npv_bar_colors = [COLOR_CRITICAL if v < 0 else battery_color for v in well_econ["NPV"]]
    metric_bar_colors = {"qi": battery_color, "EUR": battery_color, "NPV": npv_bar_colors}

    for col, metric in enumerate(["qi", "EUR", "NPV"], start=1):
        fig.add_trace(
            go.Bar(
                x=well_econ["hc_sequence"],
                y=well_econ[metric],
                marker_color=metric_bar_colors[metric],
                name="This well",
                showlegend=(col == 1),
            ),
            row=1,
            col=col,
        )
        fig.add_trace(
            go.Scatter(
                x=relevant_medians["hc_sequence"],
                y=relevant_medians[metric],
                mode="lines+markers",
                line=dict(color=COLOR_TEXT_MUTED, dash="dash"),
                marker=dict(size=6),
                name="Battery median",
                showlegend=(col == 1),
            ),
            row=1,
            col=col,
        )

    fig.update_xaxes(title_text="Cycle (chronological)", dtick=1)
    fig.update_layout(
        height=340,
        margin=dict(l=10, r=10, t=40, b=10),
        paper_bgcolor=COLOR_SURFACE,
        plot_bgcolor=COLOR_SURFACE,
        font=dict(color=COLOR_TEXT_SECONDARY),
        legend=dict(orientation="h", yanchor="bottom", y=1.12, x=0),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Bars: this well's own value per cycle, in order. Dashed line: the battery median at each "
        "cycle position (see Glossary: Battery median). Cycle positions here count only "
        "high-confidence cycles, so they may not match the cycle numbers in the production chart above."
    )


def render_degradation_panel(battery: str, well_id: str) -> None:
    section_header("Cycle-over-cycle degradation")

    econ = load_economics()
    well_econ = econ[(econ["Battery"] == battery) & (econ["FromToID"] == well_id)].sort_values("hc_sequence")

    if len(well_econ) < 2:
        n = len(well_econ)
        cycle_word = "cycle" if n == 1 else "cycles"
        with st.container(border=True):
            st.markdown(
                f"This well only has {n} high-confidence {cycle_word}, not enough to show a degradation "
                "trend. At least 2 high-confidence cycles are needed to compare cycle-over-cycle."
            )
        return

    battery_medians = battery_median_by_position(battery)
    render_degradation_chart(battery, well_econ, battery_medians)


# --- Economics what-if panel ----------------------------------------------------


def render_economics_whatif_panel(battery: str, well_id: str) -> None:
    section_header("Economics: what if?")

    econ = load_economics()
    well_econ = econ[(econ["Battery"] == battery) & (econ["FromToID"] == well_id)].sort_values("cycle_number")

    if well_econ.empty:
        with st.container(border=True):
            st.markdown("This well has no high-confidence cycles, so there's nothing to run economics on.")
        return

    default_assumptions = load_default_assumptions()
    slug = battery_slug(battery)

    slider_col1, slider_col2 = st.columns(2)
    with slider_col1:
        wti_price = st.slider(
            "WTI price ($/bbl)",
            min_value=20.0,
            max_value=150.0,
            value=round(float(default_assumptions.wti_price.value), 1),
            step=0.5,
            help=glossary_help("WTI"),
            key=f"whatif_wti_{slug}_{well_id}",
        )
    with slider_col2:
        discount_rate_pct = st.slider(
            "Discount rate (%)",
            min_value=0.0,
            max_value=30.0,
            value=round(float(default_assumptions.discount_rate.value * 100), 1),
            step=0.5,
            help=glossary_help("Discount rate"),
            key=f"whatif_rate_{slug}_{well_id}",
        )

    whatif = recompute_well_economics(battery, well_id, wti_price, discount_rate_pct)
    whatif = whatif.merge(well_econ[["cycle_number", "EUR"]], on="cycle_number", how="left")

    headline_total_npv = well_econ["NPV"].sum()
    whatif_total_npv = whatif["NPV"].sum()
    delta = whatif_total_npv - headline_total_npv
    delta_sign = "+" if delta >= 0 else ""

    metric_tile(
        "Total NPV at these assumptions",
        f"${whatif_total_npv:,.0f}",
        help_text=glossary_help("NPV"),
        sublabel=f"headline (dashboard default): ${headline_total_npv:,.0f} ({delta_sign}{delta:,.0f})",
        accent_color=BATTERY_COLORS[battery],
        key=f"whatif_total_{slug}_{well_id}",
    )

    display = pd.DataFrame(
        {
            "cycle #": whatif["cycle_number"].astype(str),
            "model": whatif["model"],
            "EUR": whatif["EUR"].map(lambda v: f"{v:,.0f}" if pd.notna(v) else "(n/a)"),
            "NPV (what if)": whatif["NPV"].map(lambda v: f"${v:,.0f}" if pd.notna(v) else "(n/a)"),
            # IRR is a root-finding solution over a handful of sparse monthly cash
            # flows, not a bounded metric — a cycle with a tiny or front-loaded cost
            # basis can solve to a technically-correct but meaningless four- or
            # five-digit percentage. Past 500% it's not telling you anything IRR is
            # meant to convey, so it's shown as a flag rather than a fake-precise number.
            "IRR (what if)": whatif["IRR"].map(
                lambda v: "(n/a)" if pd.isna(v) else (">500%, not meaningful" if v > 5.0 else f"{v * 100:.0f}%")
            ),
        }
    )
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "cycle #": st.column_config.TextColumn(
                "cycle #", help="Which cycle this row describes, in chronological order."
            ),
            "model": st.column_config.TextColumn(
                "model", help="Which Arps decline shape fit best (see Glossary tab)."
            ),
            "EUR": st.column_config.TextColumn("EUR", help=glossary_help("EUR")),
            "NPV (what if)": st.column_config.TextColumn(
                "NPV (what if)", help="NPV recalculated at the price and discount rate set above."
            ),
            "IRR (what if)": st.column_config.TextColumn("IRR (what if)", help=glossary_help("IRR")),
        },
    )
    st.caption(
        "Recalculated using the price and discount rate above, not the values used elsewhere in this "
        "dashboard. Opex, steam cost, and the WCS differential stay at their dashboard defaults."
    )


def render_well_detail(battery: str, well_id: str) -> None:
    color = BATTERY_COLORS[battery]
    st.markdown(
        f'<span class="battery-tag" style="background:{color}22; color:{color};">{battery}</span>', unsafe_allow_html=True
    )
    section_header(f"Production history: {well_id}")

    chart_col, summary_col = st.columns([2, 1])
    with chart_col:
        render_production_chart(battery, well_id)
    with summary_col:
        render_well_summary_cards(battery, well_id)

    render_degradation_panel(battery, well_id)
    render_economics_whatif_panel(battery, well_id)

    with st.expander("Per-cycle detail", expanded=False):
        render_cycle_table(battery, well_id)


# --- Glossary tab ---------------------------------------------------------------


def render_glossary() -> None:
    section_header("Glossary")
    st.caption("Plain-language definitions for every term used in this dashboard.")
    for term, entry in GLOSSARY.items():
        st.markdown(f"**{term}**")
        st.markdown(entry["full"])
        st.markdown("")


# --- Page ---------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Cold Lake CSS Decline Dashboard", layout="wide")
    inject_css()
    st.title("Cold Lake CSS Decline Dashboard")

    battery, well_id = render_sidebar()

    dashboard_tab, glossary_tab = st.tabs(["Dashboard", "Glossary"])
    with dashboard_tab:
        if well_id is None:
            render_battery_overview()
        else:
            render_well_detail(battery, well_id)
    with glossary_tab:
        render_glossary()


if __name__ == "__main__":
    main()
