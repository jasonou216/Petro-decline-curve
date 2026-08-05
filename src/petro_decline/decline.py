"""Arps decline curve models (exponential, hyperbolic, harmonic) and curve fitting.

Cold Lake is a CSS (Cyclic Steam Stimulation) thermal asset: individual wells cycle
through steam/soak/produce phases and do not follow a standard Arps decline at the
well level. Decline curves are therefore fit to a *pad-level aggregate* production
time series (summed PROD-activity volumes across all producing wells on a battery/
pad, injectors excluded — see `data.aggregate_pad_production`), not to individual
wells.

The `Methodology` enum makes the fit target explicit and leaves room to add a
well-level fit later without changing these function signatures, even though only
PAD_LEVEL is implemented for now.
"""

from __future__ import annotations

from enum import Enum

import pandas as pd


class Methodology(Enum):
    """Level of aggregation the production series represents before fitting."""

    WELL_LEVEL = "well_level"  # not implemented — CSS cycling breaks well-level Arps
    PAD_LEVEL = "pad_level"  # implemented — fit to summed pad/battery monthly production


class ArpsModel(Enum):
    """Arps decline forms."""

    EXPONENTIAL = "exponential"
    HYPERBOLIC = "hyperbolic"
    HARMONIC = "harmonic"


def fit_decline(
    production: pd.DataFrame,
    model: ArpsModel,
    methodology: Methodology = Methodology.PAD_LEVEL,
) -> dict[str, float]:
    """Fit an Arps decline model to a monthly production time series.

    Args:
        production: monthly production series to fit. For `methodology=PAD_LEVEL`,
            this is the battery/pad-aggregated series from
            `data.aggregate_pad_production` — summed PROD-activity volumes across
            all producing wells on the pad, excluding injectors.
        model: which Arps form to fit.
        methodology: aggregation level the `production` series represents. Only
            PAD_LEVEL is implemented; WELL_LEVEL is reserved for a future well-level
            fit and raises NotImplementedError if selected.

    Returns:
        Fitted parameters: qi (initial rate), Di (initial decline rate), and — for
        the hyperbolic model — b (decline exponent).
    """
    raise NotImplementedError
