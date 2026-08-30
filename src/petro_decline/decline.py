"""Per-cycle Arps decline fitting for Cold Lake CSS wells.

======================================================================
METHODOLOGY PIVOT — for anyone reading this file
======================================================================
Phase 1 assumed pad-level Arps: sum every producing well's volume across a
battery per month, fit one decline curve to that battery-level series.
Phase 2 ruled that out by inspection — Mahihkan's pad-level aggregate is a
flat plateau (thousands of individual wells' steam-cycle sawtooths cancel
out when summed), and Nabiye's pad-level rise turned out to be driven by
new wells coming online over time, not by any well actually declining.
Neither aggregate is a real decline curve.

Fitting a well's *raw* history directly was also ruled out: Cold Lake is CSS
(Cyclic Steam Stimulation) — a well is stimulated with steam, soaks, then
produces until the next re-stimulation, repeating many times over its life.
A raw well history is therefore a sawtooth of several independent decline
segments, not one.

What survived: detect the individual production *cycles* within each well
(a cycle = one steam-stimulation peak through decline to the next
stimulation), and fit Arps to each cycle's post-peak segment independently.
Cycle detection (peak-finding via relative/local prominence, a minimum-
volume filter, and a startup-ramp exclusion for each well's left-censored
first segment) was validated separately — see
notebooks/explore_cycle_detection.py and notebooks/detect_cycles_full.py —
against all 1,864 producer wells and a hand-reviewed random sample of near-
miss candidates. This module consumes that already-detected cycle table; it
does not redetect cycles.
======================================================================

Arps decline equations (t = months since the cycle's peak, so t=0 is the
peak itself, q(0) = qi by construction for all three forms):

    Exponential: q(t) = qi * exp(-Di * t)                    (b = 0)
    Hyperbolic:  q(t) = qi / (1 + b*Di*t)^(1/b)               (0 < b <= 2)
    Harmonic:    q(t) = qi / (1 + Di*t)                       (b = 1)

    qi — initial rate at the cycle's peak (m3/month).
    Di — nominal initial decline rate: the fractional rate of decline at
         t=0 (per month). Larger Di means a steeper initial drop-off.
    b  — hyperbolic decline exponent, governing how much the decline rate
         itself slows down over time. b=0 is a constant fractional decline
         (exponential); b=1 (harmonic) flattens out the most; values above 1
         flatten even more aggressively and are rarely physical, which is
         why b is bounded to [0, 2] here rather than left unconstrained.

All three forms are fit independently per cycle and the best one is kept by
AIC (see `fit_cycle`) — this mirrors standard decline-curve-analysis
practice of comparing Arps forms per well/segment rather than assuming one
form for an entire dataset.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

# --- Model definitions -------------------------------------------------

# Hyperbolic's lower bound is just above 0, not exactly 0: q(t) at b=0 is a
# 0/0 indeterminate form in this parameterization (1/b blows up), and the
# exponential model already covers that limiting case as its own fit.
B_BOUNDS = (1e-6, 2.0)

# Minimum points required to attempt a model = its parameter count (k) + 2,
# i.e. at least 2 residual degrees of freedom. This isn't just "enough to
# solve the equations" (k points does that with zero residual DOF): with
# n == k, curve_fit can pass through every point exactly, RSS collapses to
# ~0, and AIC — even AICc — can't tell a genuine fit from an
# over-parameterized one with nothing left to check it against. Requiring
# n >= k + 2 also keeps AICc's correction term (below) always defined.

# Thresholds for flagging a fit low_confidence — starting guesses for human
# review, not validated cutoffs. MAX_PLAUSIBLE_DI: a nominal monthly decline
# above 200% means the rate would be expected to fall by more than half
# within a single month, which is steep even for a fresh post-steam decline.
MIN_ACCEPTABLE_R2 = 0.5
MAX_PLAUSIBLE_DI = 2.0
B_BOUNDARY_EPSILON = 1e-3  # b within this of a bound means the optimizer is pinned, not converged


class ArpsModel(Enum):
    """Arps decline forms."""

    EXPONENTIAL = "exponential"
    HYPERBOLIC = "hyperbolic"
    HARMONIC = "harmonic"


def _exponential(t: np.ndarray, qi: float, di: float) -> np.ndarray:
    return qi * np.exp(-di * t)


def _harmonic(t: np.ndarray, qi: float, di: float) -> np.ndarray:
    return qi / (1 + di * t)


def _hyperbolic(t: np.ndarray, qi: float, di: float, b: float) -> np.ndarray:
    return qi / (1 + b * di * t) ** (1 / b)


_ARPS_FUNCTIONS = {
    ArpsModel.EXPONENTIAL: _exponential,
    ArpsModel.HARMONIC: _harmonic,
    ArpsModel.HYPERBOLIC: _hyperbolic,
}


# --- Single-model fitting -----------------------------------------------


def _initial_guess(t: np.ndarray, q: np.ndarray) -> tuple[float, float]:
    """Data-driven starting point for (qi, Di): qi from the peak itself, Di
    from the average exponential decline rate implied by the first and last
    points — a better curve_fit starting point than a fixed guess across
    cycles that can differ by orders of magnitude in scale and length.
    """
    qi0 = max(float(q[0]), 1e-3)
    if len(q) > 1 and q[-1] > 0:
        di0 = max(float(np.log(qi0 / q[-1]) / t[-1]), 1e-3)
    else:
        di0 = 0.1
    return qi0, di0


def _fit_single_model(t: np.ndarray, q: np.ndarray, model: ArpsModel) -> dict | None:
    """Fit one Arps form to (t, q) via nonlinear least squares.

    Returns None if there aren't enough points for this model's parameter
    count (n < k + 2) or curve_fit can't converge — callers should treat
    either as "this form doesn't work for this cycle" rather than a hard
    error, since trying all three forms and keeping the survivors is the
    whole point.
    """
    func = _ARPS_FUNCTIONS[model]
    k = 3 if model is ArpsModel.HYPERBOLIC else 2
    n = len(t)
    if n < k + 2:
        return None

    qi0, di0 = _initial_guess(t, q)

    if model is ArpsModel.HYPERBOLIC:
        p0 = [qi0, di0, 1.0]
        lower, upper = [0.0, 0.0, B_BOUNDS[0]], [np.inf, np.inf, B_BOUNDS[1]]
    else:
        p0 = [qi0, di0]
        lower, upper = [0.0, 0.0], [np.inf, np.inf]

    try:
        params, _covariance = curve_fit(func, t, q, p0=p0, bounds=(lower, upper), maxfev=5000)
    except RuntimeError:
        return None

    residuals = q - func(t, *params)
    rss = float(np.sum(residuals**2))
    tss = float(np.sum((q - q.mean()) ** 2))
    r_squared = 1.0 if rss == 0 else (1 - rss / tss if tss > 0 else 0.0)

    aic = n * np.log(max(rss, 1e-9) / n) + 2 * k  # rss floored to avoid log(0) on a perfect fit
    # Small-sample correction (AICc): plain AIC is badly biased when n is close
    # to k, exactly the regime a short cycle puts hyperbolic's 3 parameters in
    # — with few points, an extra parameter can drive RSS near zero without
    # actually being justified, and uncorrected AIC rewards that. The n >= k+2
    # gate above guarantees n - k - 1 >= 1, so this correction is always defined.
    aicc = aic + (2 * k * (k + 1)) / (n - k - 1)

    qi, di = float(params[0]), float(params[1])
    b = float(params[2]) if model is ArpsModel.HYPERBOLIC else (1.0 if model is ArpsModel.HARMONIC else 0.0)
    return {"model": model, "qi": qi, "Di": di, "b": b, "r_squared": r_squared, "aic": aicc}


# --- Per-cycle fitting ----------------------------------------------------


def fit_cycle(t: np.ndarray, q: np.ndarray, short_cycle: bool) -> dict:
    """Fit exponential, hyperbolic, and harmonic Arps to one cycle's post-peak
    segment and return the best (lowest-AIC) fit, with a low_confidence flag.

    AICc, not raw R², picks the winner: hyperbolic has an extra free parameter
    (b) and will almost always match or beat the nested exponential/harmonic
    fits on R² alone, so selecting by R² would systematically favor it
    regardless of whether the extra parameter is actually earning its keep.
    AICc penalizes that — the small-sample-corrected version of AIC, not
    plain AIC, because plain AIC is itself biased toward extra parameters
    when the point count is close to the parameter count (exactly the
    regime a short cycle puts hyperbolic's 3 parameters in). Each model is
    only attempted with at least 2 residual degrees of freedom (n >= k + 2),
    so a 3-point cycle can no longer "fit" a 3-parameter curve with nothing
    left to check it against. R² is still returned for the winning model,
    since it's the more intuitive "how good is this fit" number for review.

    Args:
        t: months since the cycle's peak (0, 1, 2, ...).
        q: observed monthly rate at each t (same units as production).
        short_cycle: whether this cycle was flagged short (<6 months) during
            detection — passed through so it always contributes to
            low_confidence rather than being silently trusted just because
            curve_fit happened to converge.

    Returns:
        Dict with model (str or None), qi, Di, b, r_squared (NaN if no model
        fit), low_confidence (bool), and low_confidence_reason (str,
        semicolon-separated list of the specific reasons, empty if none).
    """
    fits = []
    for model in ArpsModel:
        fit = _fit_single_model(t, q, model)
        if fit is not None:
            fits.append(fit)

    if not fits:
        # Exponential/harmonic (k=2) need n>=4; hyperbolic (k=3) needs n>=5.
        # If even the least-demanding model couldn't be attempted, it's a
        # data problem, not a convergence problem.
        reason = "too few data points to fit" if len(q) < 4 else "no Arps form converged"
        return {
            "model": None,
            "qi": float("nan"),
            "Di": float("nan"),
            "b": float("nan"),
            "r_squared": float("nan"),
            "low_confidence": True,
            "low_confidence_reason": reason,
        }

    best = min(fits, key=lambda fit: fit["aic"])

    reasons = []
    if short_cycle:
        reasons.append("short cycle (<6mo)")
    if best["r_squared"] < MIN_ACCEPTABLE_R2:
        reasons.append(f"low R2 ({best['r_squared']:.2f})")
    if best["Di"] > MAX_PLAUSIBLE_DI:
        reasons.append(f"very high Di ({best['Di']:.2f}/month)")
    if best["model"] is ArpsModel.HYPERBOLIC and (
        best["b"] < B_BOUNDS[0] + B_BOUNDARY_EPSILON or best["b"] > B_BOUNDS[1] - B_BOUNDARY_EPSILON
    ):
        reasons.append(f"b pinned at bound ({best['b']:.3f})")

    return {
        "model": best["model"].value,
        "qi": best["qi"],
        "Di": best["Di"],
        "b": best["b"],
        "r_squared": best["r_squared"],
        "low_confidence": len(reasons) > 0,
        "low_confidence_reason": "; ".join(reasons),
    }


def fit_all_cycles(cycles_df: pd.DataFrame, well_series_by_battery: dict[str, dict[str, pd.Series]]) -> pd.DataFrame:
    """Fit Arps decline to every fittable cycle in `cycles_df`.

    Startup-ramp cycles (`is_startup_ramp == True`) are excluded — they run
    from a well's first reported month to its first detected re-stimulation,
    which is initial production coming online, not a post-stimulation
    decline, and fitting Arps to a rising trend doesn't mean anything.

    Args:
        cycles_df: one row per detected cycle (from
            notebooks/detect_cycles_full.py's cycles_full.csv), with columns
            Battery, FromToID, start, end, duration_months, short_cycle,
            is_final_cycle, is_startup_ramp.
        well_series_by_battery: {battery_name: {FromToID: OIL series}} —
            each series as returned by `data.well_oil_series`, keyed by well,
            grouped by battery so the same well ID can't collide across
            batteries.

    Returns:
        One row per fitted cycle: Battery, FromToID, cycle_number (1-based,
        counting only fittable cycles for that well), cycle_start,
        duration_months, short_cycle, model, qi, Di, b, r_squared,
        low_confidence, low_confidence_reason.
    """
    fittable = cycles_df[~cycles_df["is_startup_ramp"]].copy()
    fittable["start"] = pd.to_datetime(fittable["start"])
    fittable["end"] = pd.to_datetime(fittable["end"])
    fittable = fittable.sort_values(["Battery", "FromToID", "start"])
    fittable["cycle_number"] = fittable.groupby(["Battery", "FromToID"]).cumcount() + 1

    rows = []
    for row in fittable.itertuples(index=False):
        series = well_series_by_battery[row.Battery][row.FromToID]
        segment = series.loc[row.start : row.end]
        q_raw = segment.to_numpy()
        t_raw = np.arange(len(q_raw), dtype=float)

        # data.well_oil_series zero-fills months absent from Petrinex (soak /
        # shut-in), and those aren't decline observations — a mid-cycle
        # workover shut-in, for instance, isn't the reservoir declining to
        # zero, it's downtime. Dropping them keeps the fit shaped by actual
        # production; t stays the true elapsed month so the remaining
        # points' timing is still correct, just not contiguous.
        producing = q_raw > 0
        t, q = t_raw[producing], q_raw[producing]

        fit = fit_cycle(t, q, short_cycle=row.short_cycle)
        rows.append(
            {
                "Battery": row.Battery,
                "FromToID": row.FromToID,
                "cycle_number": row.cycle_number,
                "cycle_start": row.start,
                "duration_months": row.duration_months,
                "short_cycle": row.short_cycle,
                **fit,
            }
        )

    return pd.DataFrame(rows)


def predict(t: np.ndarray, model: str, qi: float, di: float, b: float) -> np.ndarray:
    """Evaluate a fitted Arps curve at the given t (months since peak) — for plotting."""
    arps_model = ArpsModel(model)
    func = _ARPS_FUNCTIONS[arps_model]
    if arps_model is ArpsModel.HYPERBOLIC:
        return func(t, qi, di, b)
    return func(t, qi, di)
