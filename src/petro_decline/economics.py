"""Basic NPV/IRR/payback economics for per-cycle Arps decline fits.

Scope: OIL revenue only, consistent with the rest of this project (gas and
water were never priced or modeled economically here). Illustrative modeling
for a portfolio project — not investment advice, not a real capital
allocation analysis.

Cash flows are built from each cycle's *monthly* production (via
`decline.predict`, using the fitted qi/Di/b), not from a single lump-sum
EUR number. NPV/IRR/payback all fundamentally depend on the *timing* of
cash flows, not just the total volume recovered — a lump-sum EUR alone
can't produce a meaningful IRR or payback period at all, since both need to
know how quickly (or slowly) the volume actually arrives. The monthly
series still integrates to the same EUR `petro_decline.eur.cycle_eur`
already computed for Phase 4.

Every price/cost/rate input is an `Assumption` (value + source +
last_updated), not a bare number — nothing here is a hardcoded magic
constant. WTI price is fetched live from the EIA API (`fetch_wti_price`);
everything else comes from config.yaml. `load_assumptions()` assembles the
full `EconomicAssumptions` and is the one function callers should normally
use; `print_summary()` shows every input's value/source/last_updated/
live-vs-fallback status so a report never presents a number without saying
where it came from.

Low-confidence cycles are not filtered here — that exclusion already
happened upstream (see notebooks/cycle_degradation_comparison.py, which
produced high_confidence_cycles_with_eur.csv). Every function in this
module assumes its input is already high-confidence-only; the exclusion is
the caller's responsibility, same as it was in Phase 4.
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yaml
from dotenv import load_dotenv
from scipy.optimize import brentq

from petro_decline.decline import predict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")  # picks up EIA_API_KEY regardless of the caller's working directory

BBL_PER_M3 = 6.28981  # standard oil conversion factor (1 bbl = 0.158987 m3)

DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"

EIA_API_URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
EIA_WTI_SERIES = "RWTC"  # Cushing, OK WTI Spot Price FOB, Dollars per Barrel, Daily


@dataclass(frozen=True)
class Assumption:
    """A single economic input, carrying where it came from and how current it is."""

    value: float
    source: str
    last_updated: str  # 'YYYY-MM-DD', or the EIA data date when fetched live


@dataclass(frozen=True)
class EconomicAssumptions:
    """Every economics input for one scenario. Build via `load_assumptions()`, not by hand."""

    wti_price: Assumption  # $/bbl
    wcs_differential: Assumption  # $/bbl
    discount_rate: Assumption  # annual, as a fraction (0.10 = 10%/year)
    opex_per_bbl: Assumption  # $/bbl
    steam_cost_per_cycle: Assumption  # $ per cycle, incurred at the cycle's start (t=0)

    @property
    def wcs_price_usd_per_bbl(self) -> float:
        return self.wti_price.value - self.wcs_differential.value

    @property
    def discount_rate_monthly(self) -> float:
        return (1 + self.discount_rate.value) ** (1 / 12) - 1

    def print_summary(self) -> None:
        """Print every input's value, source, and last_updated — so a report never
        shows a number without saying whether it's live data or a dated assumption.
        """
        print(f"WCS price (derived): ${self.wcs_price_usd_per_bbl:.2f}/bbl = WTI - differential")
        for label, assumption in [
            ("WTI price", self.wti_price),
            ("WCS differential", self.wcs_differential),
            ("Discount rate", self.discount_rate),
            ("Opex", self.opex_per_bbl),
            ("Steam cost/cycle", self.steam_cost_per_cycle),
        ]:
            print(f"  {label}: {assumption.value} (source: {assumption.source}; last updated: {assumption.last_updated})")


# --- Loading assumptions: live WTI + config.yaml for everything else --------


class EiaApiKeyMissing(RuntimeError):
    """Raised when EIA_API_KEY isn't set — message tells the user how to fix it."""


def fetch_wti_price(api_key: str | None = None, timeout: int = 30) -> Assumption:
    """Fetch the latest daily Cushing WTI spot price from the EIA API.

    Args:
        api_key: EIA API key. Defaults to the EIA_API_KEY environment variable.
        timeout: request timeout in seconds.

    Returns:
        An Assumption with the live price, source="EIA API (live)", and
        last_updated set to the date EIA reports for that price.

    Raises:
        EiaApiKeyMissing: no API key was provided or set in the environment.
        requests.RequestException: the API call itself failed.
        ValueError: the API responded but returned no data (e.g. wrong series ID).
    """
    key = api_key or os.environ.get("EIA_API_KEY")
    if not key:
        raise EiaApiKeyMissing(
            "EIA_API_KEY is not set. Sign up for a free key at "
            "https://www.eia.gov/opendata/register.php, then set it as an "
            "environment variable (EIA_API_KEY) before running this."
        )

    params = {
        "api_key": key,
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": EIA_WTI_SERIES,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 1,
    }
    response = requests.get(EIA_API_URL, params=params, timeout=timeout)
    response.raise_for_status()

    records = response.json().get("response", {}).get("data", [])
    if not records:
        raise ValueError(
            f"EIA API returned no data for series '{EIA_WTI_SERIES}' — the series ID may be wrong "
            "or the API response shape changed. Check https://www.eia.gov/opendata/browser/petroleum/pri/spt."
        )

    latest = records[0]
    return Assumption(value=float(latest["value"]), source="EIA API (live)", last_updated=str(latest["period"]))


def load_wti_price(fallback: Assumption, api_key: str | None = None) -> Assumption:
    """Live WTI price with a fallback: tries `fetch_wti_price`, and on *any*
    failure (missing key, network error, bad response) prints a warning and
    returns `fallback` instead, rather than crashing the whole economics run.
    """
    try:
        return fetch_wti_price(api_key=api_key)
    except (EiaApiKeyMissing, requests.RequestException, ValueError) as exc:
        print(f"WARNING: live WTI price unavailable ({exc}) — using fallback (${fallback.value}/bbl).")
        return fallback


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """Read config.yaml into a plain dict of {field_name: {value, source, last_updated}}."""
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_assumptions(config_path: Path = DEFAULT_CONFIG_PATH, eia_api_key: str | None = None) -> EconomicAssumptions:
    """Build a full EconomicAssumptions: WTI live (with config fallback), everything else from config.yaml."""
    config = load_config(config_path)

    def assumption_from_config(key: str) -> Assumption:
        entry = config[key]
        return Assumption(value=entry["value"], source=entry["source"], last_updated=entry["last_updated"])

    wti_fallback = assumption_from_config("wti_price_fallback")
    wti_price = load_wti_price(fallback=wti_fallback, api_key=eia_api_key)

    return EconomicAssumptions(
        wti_price=wti_price,
        wcs_differential=assumption_from_config("wcs_differential"),
        discount_rate=assumption_from_config("discount_rate"),
        opex_per_bbl=assumption_from_config("opex_per_bbl"),
        steam_cost_per_cycle=assumption_from_config("steam_cost_per_cycle"),
    )


# --- Per-cycle cash flow, NPV, IRR, payback --------------------------------


def cycle_cash_flows(model: str, qi: float, di: float, b: float, duration_months: int, assumptions: EconomicAssumptions) -> np.ndarray:
    """Monthly net cash flow for one cycle, t=0..duration_months-1.

    t=0 combines the cycle's first (peak) month of production with the
    re-stimulation cost — both happen at the moment the well comes back on
    after steaming, which is exactly what t=0 represents in every fit in
    this project.
    """
    t = np.arange(duration_months, dtype=float)
    monthly_oil_bbl = predict(t, model, qi, di, b) * BBL_PER_M3
    net_revenue = monthly_oil_bbl * (assumptions.wcs_price_usd_per_bbl - assumptions.opex_per_bbl.value)

    cash_flows = net_revenue.copy()
    cash_flows[0] -= assumptions.steam_cost_per_cycle.value
    return cash_flows


def npv(cash_flows: np.ndarray, assumptions: EconomicAssumptions) -> float:
    """Net present value of a monthly cash flow series, discounted to t=0."""
    periods = np.arange(len(cash_flows))
    return float(np.sum(cash_flows / (1 + assumptions.discount_rate_monthly) ** periods))


def irr(cash_flows: np.ndarray) -> float:
    """Annualized internal rate of return via root-finding on NPV(rate) == 0.

    Returns NaN if the cash flow series never changes sign — a cycle that's
    never profitable (or never costs anything) has no IRR, not an IRR of 0%.
    """
    if np.all(cash_flows <= 0) or np.all(cash_flows >= 0):
        return float("nan")

    def npv_at_monthly_rate(monthly_rate: float) -> float:
        periods = np.arange(len(cash_flows))
        return float(np.sum(cash_flows / (1 + monthly_rate) ** periods))

    try:
        monthly_irr = brentq(npv_at_monthly_rate, -0.99, 10.0)
    except ValueError:
        return float("nan")
    return (1 + monthly_irr) ** 12 - 1


def payback_months(cash_flows: np.ndarray) -> float:
    """Simple (undiscounted) payback period, in months. NaN if never recovered within the cycle."""
    cumulative = np.cumsum(cash_flows)
    recovered = np.where(cumulative >= 0)[0]
    if len(recovered) == 0:
        return float("nan")
    return float(recovered[0])


def cycle_economics(row: pd.Series, assumptions: EconomicAssumptions) -> dict:
    """NPV/IRR/payback for one cycle row (needs model, qi, Di, b, duration_months)."""
    cash_flows = cycle_cash_flows(row["model"], row["qi"], row["Di"], row["b"], int(row["duration_months"]), assumptions)
    return {"NPV": npv(cash_flows, assumptions), "IRR": irr(cash_flows), "payback_months": payback_months(cash_flows)}


def compute_cycle_economics(cycles: pd.DataFrame, assumptions: EconomicAssumptions) -> pd.DataFrame:
    """NPV/IRR/payback for every row in `cycles` (caller is responsible for pre-filtering to high-confidence)."""
    results = cycles.apply(lambda row: pd.Series(cycle_economics(row, assumptions)), axis=1)
    return pd.concat([cycles.reset_index(drop=True), results.reset_index(drop=True)], axis=1)


# --- Well-level rollup -------------------------------------------------------


def well_level_summary(cycle_econ: pd.DataFrame) -> pd.DataFrame:
    """One row per well: NPV summed across its fitted (high-confidence) cycles."""
    return (
        cycle_econ.groupby(["Battery", "FromToID"])
        .agg(n_cycles=("NPV", "count"), total_NPV=("NPV", "sum"), total_EUR=("EUR", "sum"))
        .reset_index()
        .sort_values("total_NPV", ascending=False)
    )


# --- Sensitivity --------------------------------------------------------------


def sensitivity_table(
    cycles: pd.DataFrame,
    base_assumptions: EconomicAssumptions,
    price_scenarios: dict[str, float],
    discount_rates: list[float],
) -> pd.DataFrame:
    """Total NPV across `cycles` for every (price scenario x discount rate) combination.

    Args:
        cycles: cycle rows to price (high-confidence only, caller's responsibility).
        base_assumptions: everything except price/discount rate is held fixed at these values.
        price_scenarios: {label: wti_price_usd_per_bbl}.
        discount_rates: annual discount rates to sweep.

    Returns:
        One row per (price scenario, discount rate) with the resulting total NPV.
    """
    rows = []
    for price_label, wti_price in price_scenarios.items():
        wti_assumption = dataclasses.replace(base_assumptions.wti_price, value=wti_price, source="sensitivity scenario")
        for rate in discount_rates:
            rate_assumption = dataclasses.replace(base_assumptions.discount_rate, value=rate, source="sensitivity scenario")
            scenario = dataclasses.replace(base_assumptions, wti_price=wti_assumption, discount_rate=rate_assumption)
            econ = compute_cycle_economics(cycles, scenario)
            rows.append(
                {
                    "price_scenario": price_label,
                    "wti_price_usd_per_bbl": wti_price,
                    "wcs_price_usd_per_bbl": scenario.wcs_price_usd_per_bbl,
                    "discount_rate_annual": rate,
                    "total_NPV": econ["NPV"].sum(),
                }
            )
    return pd.DataFrame(rows)
