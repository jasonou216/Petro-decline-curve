"""Unit tests for src/petro_decline/economics.py: NPV, IRR, payback."""

from __future__ import annotations

import numpy as np
import pytest

from petro_decline.economics import Assumption, EconomicAssumptions, irr, npv, payback_months


def _assumptions(**overrides) -> EconomicAssumptions:
    """Small helper: sane default assumptions, override just what a test needs."""
    defaults = dict(
        wti_price=Assumption(80.0, "test", "2026-01-01"),
        wcs_differential=Assumption(17.0, "test", "2026-01-01"),
        discount_rate=Assumption(0.10, "test", "2026-01-01"),
        opex_per_bbl=Assumption(13.0, "test", "2026-01-01"),
        steam_cost_per_cycle=Assumption(200_000.0, "test", "2026-01-01"),
    )
    defaults.update(overrides)
    return EconomicAssumptions(**defaults)


def test_npv_at_zero_discount_rate_equals_undiscounted_sum():
    assumptions = _assumptions(discount_rate=Assumption(0.0, "test", "2026-01-01"))
    cash_flows = np.array([-100_000.0, 40_000.0, 40_000.0, 40_000.0])

    assert npv(cash_flows, assumptions) == pytest.approx(cash_flows.sum())


def test_npv_discounts_future_cash_flows_below_face_value():
    assumptions = _assumptions()
    cash_flows = np.array([0.0, 100_000.0])  # all value one period out

    result = npv(cash_flows, assumptions)

    assert 0 < result < 100_000.0


def test_wcs_price_is_wti_minus_differential():
    assumptions = _assumptions(
        wti_price=Assumption(83.9, "test", "2026-01-01"),
        wcs_differential=Assumption(17.0, "test", "2026-01-01"),
    )
    assert assumptions.wcs_price_usd_per_bbl == pytest.approx(66.9)


def test_irr_recovers_a_known_rate():
    """A simple invest-then-single-payoff cash flow has a closed-form IRR —
    confirm brentq actually finds it, not just that it returns *something*.
    """
    monthly_rate_true = 0.02
    cash_flows = np.array([-10_000.0, 0.0, 0.0, 10_000.0 * (1 + monthly_rate_true) ** 3])

    annual_irr = irr(cash_flows)
    expected_annual = (1 + monthly_rate_true) ** 12 - 1

    assert annual_irr == pytest.approx(expected_annual, rel=0.02)


def test_irr_is_nan_when_cash_flow_never_goes_negative():
    """A cycle that's profitable from month zero onward (common for the biggest,
    highest-qi wells here) has no root to find — IRR should come back NaN, not 0%
    or some other placeholder that reads as a real answer.
    """
    cash_flows = np.array([50_000.0, 40_000.0, 30_000.0])
    assert np.isnan(irr(cash_flows))


def test_irr_is_nan_when_cash_flow_never_turns_positive():
    cash_flows = np.array([-50_000.0, -10_000.0, -5_000.0])
    assert np.isnan(irr(cash_flows))


def test_payback_months_finds_the_breakeven_period():
    cash_flows = np.array([-100_000.0, 30_000.0, 30_000.0, 30_000.0, 30_000.0])
    # cumulative: -100k, -70k, -40k, -10k, +20k -> breaks even at index 4
    assert payback_months(cash_flows) == 4


def test_payback_months_nan_if_never_recovered():
    cash_flows = np.array([-100_000.0, 10_000.0, 10_000.0])
    assert np.isnan(payback_months(cash_flows))
