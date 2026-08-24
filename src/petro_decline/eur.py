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
"""

from __future__ import annotations

import numpy as np

from petro_decline.decline import ArpsModel

_B_NEAR_ONE = 1e-6  # within this of b=1, use the harmonic formula to avoid a 1/(1-b) blowup


def cycle_eur(model: str, qi: float, di: float, b: float, duration_months: float) -> float:
    """Cumulative production from a fitted Arps curve, integrated over its cycle's duration.

    Args:
        model: 'exponential', 'harmonic', or 'hyperbolic'.
        qi: initial rate at the cycle's peak.
        di: nominal initial decline rate (per month).
        b: hyperbolic exponent (ignored for exponential/harmonic).
        duration_months: months to integrate over (the cycle's own duration).

    Returns:
        Cumulative volume over [0, duration_months], same units as qi (e.g.
        m3/month) times a month.
    """
    arps_model = ArpsModel(model)
    t = duration_months

    if di == 0:
        return qi * t

    if arps_model is ArpsModel.EXPONENTIAL:
        return qi / di * (1 - np.exp(-di * t))

    if arps_model is ArpsModel.HARMONIC or abs(b - 1.0) < _B_NEAR_ONE:
        return qi / di * np.log(1 + di * t)

    return qi / (di * (b - 1)) * ((1 + b * di * t) ** (1 - 1 / b) - 1)
