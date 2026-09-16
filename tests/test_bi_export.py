"""Unit tests for src/petro_decline/bi_export.py."""

from __future__ import annotations

import pandas as pd
import pytest

from petro_decline.bi_export import build_dim_battery, build_dim_well, build_fact_cycle


@pytest.fixture
def cycles():
    return pd.DataFrame(
        {
            "Battery": ["B1", "B1", "B1"],
            "FromToID": ["W1", "W1", "W2"],  # W1: 2 rows (dup, as cycles_full.csv has), W2: 1
        }
    )


@pytest.fixture
def fits():
    return pd.DataFrame(
        {
            "Battery": ["B1", "B1"],
            "FromToID": ["W1", "W1"],
            "cycle_number": [1, 2],
            "cycle_start": ["2023-01-01", "2023-06-01"],
            "duration_months": [5, 6],
            "model": ["exponential", "harmonic"],
            "qi": [500.0, 300.0],
            "Di": [0.2, 0.1],
            "b": [0.0, 1.0],
            "r_squared": [0.8, 0.3],
            "low_confidence": [False, True],
            "low_confidence_reason": ["", "low R2 (0.30)"],
        }
    )
    # W2 has zero fittable cycles (e.g. startup-ramp-only), deliberately absent from `fits`.


@pytest.fixture
def econ():
    return pd.DataFrame(
        {
            "Battery": ["B1"],
            "FromToID": ["W1"],
            "cycle_number": [1],
            "EUR": [4000.0],
            "NPV": [1_200_000.0],
        }
    )
    # Only cycle 1 (the high-confidence one) is priced, matching how
    # decline_economics_full.csv never has a row for a low-confidence cycle.


def test_dim_well_includes_well_with_zero_fittable_cycles(cycles, fits):
    dim_well = build_dim_well(cycles, fits)

    assert set(dim_well["WellID"]) == {"W1", "W2"}
    w2 = dim_well[dim_well["WellID"] == "W2"].iloc[0]
    assert w2["TotalCycles"] == 0
    assert w2["TotalHighConfidenceCycles"] == 0

    w1 = dim_well[dim_well["WellID"] == "W1"].iloc[0]
    assert w1["TotalCycles"] == 2
    assert w1["TotalHighConfidenceCycles"] == 1  # only cycle 1 is high confidence


def test_dim_battery_averages_over_every_well_including_zero_cycle_ones(cycles, fits):
    dim_well = build_dim_well(cycles, fits)
    dim_battery = build_dim_battery(dim_well)

    row = dim_battery.iloc[0]
    assert row["TotalWells"] == 2
    # (2 + 0) / 2 wells = 1.0 total cycles/well; (1 + 0) / 2 = 0.5 HC cycles/well
    assert row["AvgCyclesPerWell"] == pytest.approx(1.0)
    assert row["AvgHighConfidenceCyclesPerWell"] == pytest.approx(0.5)


def test_fact_cycle_eur_npv_blank_for_low_confidence_cycles(fits, econ):
    fact_cycle = build_fact_cycle(fits, econ)

    assert len(fact_cycle) == 2  # both fittable cycles, high and low confidence

    high_conf = fact_cycle[fact_cycle["CycleNumber"] == 1].iloc[0]
    assert bool(high_conf["IsHighConfidence"]) is True
    assert high_conf["EUR"] == pytest.approx(4000.0)
    assert high_conf["NPV"] == pytest.approx(1_200_000.0)

    low_conf = fact_cycle[fact_cycle["CycleNumber"] == 2].iloc[0]
    assert bool(low_conf["IsHighConfidence"]) is False
    assert pd.isna(low_conf["EUR"])
    assert pd.isna(low_conf["NPV"])
