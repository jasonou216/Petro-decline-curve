"""Estimated Ultimate Recovery (EUR) for fitted per-cycle Arps decline curves.

This is *cycle*-bounded EUR: the cumulative volume implied by a fitted decline
curve over that cycle's own observed duration (peak to the month before the
next re-stimulation, or to the data cutoff for a right-censored final cycle)
— not a lifetime EUR out to an economic limit or infinite time.

Two reasons that's the right scope for now, not a shortcut:
  1. The harmonic model's (b=1) cumulative integral is mathematically
     divergent as t -> infinity — "EUR to infinity" isn't just unmeasured for
     harmonic cycles, it's undefined. *Some* finite bound is unavoidable.
  2. A genuine economic-limit EUR needs a minimum economic rate or a
     price/cost cutoff, which belongs to the (not-yet-built) economics layer.
     Bounding to the cycle's own observed span avoids inventing an economic
     assumption this phase has no basis for, while still giving a EUR that's
     directly comparable across cycles of different lengths — which is
     exactly what a cycle-degradation comparison needs.

This used to be a continuous closed-form integral, integral_0^T q(t) dt. It
isn't anymore: `economics.cycle_cash_flows` builds monthly revenue from
`decline.predict(t)` evaluated at the discrete grid t = 0, 1, ..., T-1 (one
predicted rate per production month, which is how the volume is actually
reported and priced), and a continuous integral over the same window doesn't
equal that discrete sum — for any declining curve, summing the rate at the
start of each month overstates the true area under the curve for that month,
so the two numbers diverged by a few percent depending on how steep the
cycle was. Computing EUR as the same discrete sum `cycle_cash_flows` already
uses removes the mismatch entirely: EUR and the volume implied by NPV are
now built from the identical numbers, not two different approximations of
the same thing.
"""

from __future__ import annotations

import numpy as np

from petro_decline.decline import predict


def cycle_eur(model: str, qi: float, di: float, b: float, duration_months: float) -> float:
    """Cumulative production from a fitted Arps curve, summed over its cycle's
    monthly time grid, t = 0, 1, ..., duration_months - 1 — the same grid
    `economics.cycle_cash_flows` uses to build monthly revenue.

    Args:
        model: 'exponential', 'harmonic', or 'hyperbolic'.
        qi: initial rate at the cycle's peak.
        di: nominal initial decline rate (per month).
        b: hyperbolic exponent (ignored for exponential/harmonic).
        duration_months: number of months in the cycle (the cycle's own
            observed duration).

    Returns:
        Cumulative volume over the cycle, same units as qi (e.g. m3/month)
        times a month.
    """
    t = np.arange(int(duration_months), dtype=float)
    return float(np.sum(predict(t, model, qi, di, b)))
