"""Unit tests for src/petro_decline/eur.py.

The main thing worth testing here isn't the math itself (cycle_eur is a thin
wrapper around decline.predict), it's the property the whole EUR/NPV fix in
this project's history was about: EUR and the volume NPV is built from have to
be the exact same number, not two different approximations of it.
"""

from __future__ import annotations

import numpy as np
import pytest

from petro_decline.decline import predict
from petro_decline.eur import cycle_eur


@pytest.mark.parametrize("model,qi,di,b", [
    ("exponential", 500.0, 0.15, 0.0),
    ("harmonic", 300.0, 0.10, 1.0),
    ("hyperbolic", 800.0, 0.25, 0.6),
])
def test_cycle_eur_matches_manual_monthly_sum(model, qi, di, b):
    """cycle_eur should equal summing predict() over the same monthly grid by hand —
    this is the exact computation, not an approximation of it.
    """
    duration = 9
    expected = float(np.sum(predict(np.arange(duration, dtype=float), model, qi, di, b)))

    assert cycle_eur(model, qi, di, b, duration) == pytest.approx(expected)


def test_cycle_eur_matches_economics_cash_flow_volume():
    """Regression test for the bug this project's review caught: EUR used to be a
    continuous integral while economics.cycle_cash_flows built revenue from a
    discrete monthly sum of the same curve, and the two didn't agree. Confirms
    they're now built from the literal same numbers.
    """
    from petro_decline.economics import Assumption, EconomicAssumptions, cycle_cash_flows

    qi, di, b, duration = 450.0, 0.2, 0.8, 10
    assumptions = EconomicAssumptions(
        wti_price=Assumption(80.0, "test", "2026-01-01"),
        wcs_differential=Assumption(17.0, "test", "2026-01-01"),
        discount_rate=Assumption(0.10, "test", "2026-01-01"),
        opex_per_bbl=Assumption(13.0, "test", "2026-01-01"),
        steam_cost_per_cycle=Assumption(200_000.0, "test", "2026-01-01"),
    )

    eur = cycle_eur("hyperbolic", qi, di, b, duration)

    # Reverse cycle_cash_flows' math to recover the monthly oil volume (m3) it
    # priced, and confirm summing it gives back the same EUR.
    from petro_decline.economics import BBL_PER_M3

    cash_flows = cycle_cash_flows("hyperbolic", qi, di, b, duration, assumptions)
    net_revenue = cash_flows.copy()
    net_revenue[0] += assumptions.steam_cost_per_cycle.value  # undo the t=0 steam deduction
    monthly_oil_bbl = net_revenue / (assumptions.wcs_price_usd_per_bbl - assumptions.opex_per_bbl.value)
    implied_eur = float(np.sum(monthly_oil_bbl / BBL_PER_M3))

    assert implied_eur == pytest.approx(eur, rel=1e-9)


def test_cycle_eur_zero_decline_rate_is_flat_multiplication():
    """di == 0 is a degenerate edge case (constant rate forever) — should just be
    qi * duration, not blow up in the exponential/hyperbolic formulas.
    """
    assert cycle_eur("exponential", 100.0, 0.0, 0.0, 12) == pytest.approx(1200.0)
