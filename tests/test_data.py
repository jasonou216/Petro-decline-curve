"""Unit tests for src/petro_decline/data.py.

These operate on small synthetic well-level DataFrames shaped like Petrinex
output, no network access — data.py's actual Petrinex pull isn't unit-tested
here, only the pure cleaning/classification logic downstream of it.
"""

from __future__ import annotations

import pandas as pd

from petro_decline.data import identify_injectors, well_oil_series


def _well_level_row(facility, well, month, product, volume):
    return {
        "ReportingFacilityID": facility,
        "FromToID": well,
        "ProductionMonth": pd.Timestamp(month),
        "ProductID": product,
        "Volume": volume,
    }


def test_identify_injectors_flags_zero_oil_wells():
    """A well that only ever reports WATER (a steam injector) should be flagged;
    a well with real OIL volume should not.
    """
    rows = [
        _well_level_row("FAC1", "PRODUCER_WELL", "2023-01", "OIL", 500.0),
        _well_level_row("FAC1", "PRODUCER_WELL", "2023-02", "OIL", 450.0),
        _well_level_row("FAC1", "INJECTOR_WELL", "2023-01", "WATER", 1000.0),
        _well_level_row("FAC1", "INJECTOR_WELL", "2023-02", "WATER", 950.0),
    ]
    well_level = pd.DataFrame(rows)

    producers, injectors = identify_injectors(well_level)

    assert set(producers["FromToID"].unique()) == {"PRODUCER_WELL"}
    assert set(injectors["FromToID"].unique()) == {"INJECTOR_WELL"}


def test_identify_injectors_counts_a_well_with_no_oil_rows_at_all_as_zero():
    """A well that never appears in the OIL/BIT product rows at all (not even a
    zero-volume row) still has to count as zero oil, not be silently excluded
    from consideration entirely — this was a real bug caught earlier in this
    project (reindex-against-all-wells fix).
    """
    rows = [
        _well_level_row("FAC1", "NORMAL_WELL", "2023-01", "OIL", 300.0),
        # WATER_ONLY_WELL has a GAS row but never an OIL/BIT row at all.
        _well_level_row("FAC1", "WATER_ONLY_WELL", "2023-01", "GAS", 12.0),
    ]
    well_level = pd.DataFrame(rows)

    producers, injectors = identify_injectors(well_level)

    assert "WATER_ONLY_WELL" in set(injectors["FromToID"].unique())
    assert "NORMAL_WELL" in set(producers["FromToID"].unique())


def test_well_oil_series_zero_fills_gaps():
    """A month Petrinex has no record for (soak/shut-in) should come back as an
    explicit 0.0 in the reindexed series, not be silently skipped.
    """
    rows = [
        _well_level_row("FAC1", "WELL1", "2023-01", "OIL", 500.0),
        # 2023-02 missing entirely (shut-in)
        _well_level_row("FAC1", "WELL1", "2023-03", "OIL", 300.0),
    ]
    well_level = pd.DataFrame(rows)

    series = well_oil_series(well_level, "WELL1")

    assert len(series) == 3  # Jan, Feb, Mar
    assert series[pd.Timestamp("2023-01-01")] == 500.0
    assert series[pd.Timestamp("2023-02-01")] == 0.0
    assert series[pd.Timestamp("2023-03-01")] == 300.0
