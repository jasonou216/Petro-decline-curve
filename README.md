# Cold Lake CSS Decline Dashboard

Per-cycle Arps decline curve analysis and project economics for two Cold Lake CSS batteries, built on real Alberta production data (Petrinex). Live dashboard: [cold-lake-petro-decline.streamlit.app](https://cold-lake-petro-decline.streamlit.app/)

## Preview

![Figure 1: Battery overview, no well selected](screenshots/battery_overview.png)
*Landing view. Metric cards for each battery: wells analyzed, average high-confidence cycles per well, total EUR, total NPV, and negative-NPV rate at both the well and cycle level.*

![Figure 2: Well production history with fitted cycles](screenshots/well_production_cycles.png)
*Raw monthly oil for one well, with the startup ramp (violet), each cycle boundary (red, numbered), and the fitted Arps curve per cycle (green if high confidence, amber if low). This well: 6 total cycles, 67% high confidence.*

![Figure 3: Cycle-over-cycle degradation](screenshots/cycle_degradation.png)
*A single well's qi, EUR, and NPV across its own cycles, bar per cycle, against the battery median at the same cycle position (dashed line).*

![Figure 4: Economics what-if panel](screenshots/economics_whatif.png)
*Price and discount-rate sliders recompute NPV and IRR live, for the selected well only, shown separately from the dashboard's default headline numbers.*

## Why this isn't a standard decline curve project

Most decline curve projects assume a well produces continuously and just slows down over time. Cold Lake wells don't work that way.

Cold Lake bitumen is too thick to flow on its own, so operators use Cyclic Steam Stimulation (CSS): inject steam, let it soak, produce until the rate falls off, then re-steam and start over. A well can go through this cycle many times over its life.

That ruled out the usual approaches, confirmed by actually looking at the data before picking a method:

1. **Well-level continuous decline** doesn't work: wells cycle in a repeating sawtooth, not a smooth decline.
2. **Pad-level aggregation** also didn't work once plotted. Mahihkan was a flat, managed plateau; Nabiye's apparent rise was new wells coming online, not existing wells improving.
3. Settled on **per-cycle analysis**: detect each steam-soak-produce cycle per well, and fit a decline curve to each cycle on its own.

## Batteries analyzed

| Battery | Operator | Wells analyzed | High-confidence cycles | Avg. cycles/well | Total EUR (m3) | Total NPV | Wells w/ negative NPV | Cycles w/ negative NPV |
|---|---|---|---|---|---|---|---|---|
| Mahihkan Battery 02-21 | Imperial Oil | 1,457 | 1,398 | 0.96 | 3,512,331 | $1,004,184,068 | 19.2% (of 924) | 24.3% |
| Nabiye 11-23 | Imperial Oil | 281 | 477 | 1.70 | 1,711,529 | $544,001,164 | 13.6% (of 243) | 18.2% |

Combined: 71.2% of all fitted cycles are low confidence, 22.8% of high-confidence cycles carry negative NPV, and total NPV across both batteries is $1,548,185,232 (mean cycle NPV $826k, median $307k, one well alone accounting for $42.1M). EUR and production volumes are in m3, the unit Petrinex reports in.

## Theory

Arps decline: `q(t) = qi / (1 + b * Di * t)^(1/b)`, fit per cycle in three forms (exponential b=0, harmonic b=1, hyperbolic general form). The winner is chosen **by AIC, not R2**: hyperbolic's extra free parameter almost always improves raw R2 whether or not it's earning its keep, and AIC penalizes that.

EUR, per cycle: `EUR = integral from 0 to T of q(t) dt`, where T is the cycle's own observed duration in months, not an economic limit (the pipeline doesn't invent a cost/price cutoff to integrate to).

NPV, per cycle: `NPV = sum over t of [ q_t * (price - opex) / (1 + r)^t ] - steam_cost`. Price is the WCS netback (WTI minus a differential), pulled live from the EIA public API with a documented fallback in `config.yaml`.

## Methodology notes

- **Cycle detection**: peak detection on monthly oil, with relative/local prominence (a peak must clear its own preceding trough by a threshold, not the well's all-time max), a minimum 4-month spacing between cycles, and a minimum-volume filter to drop wells too small to have a meaningful signal. A well's first rise from zero is tagged as startup, not a cycle. The 40% prominence threshold was checked, not assumed: 25 random borderline (30-40%) candidates were judged by eye, and about 60% turned out to be noise, which confirmed the cutoff.
- **Confidence flagging**: a fit is low confidence if the cycle is too short, R2 is poor, or a parameter hits its bound. Most of the 71.2% low-confidence rate comes from real production being non-monotonic within a cycle (a rise, a dip, another bump) while Arps curves are strictly monotonic. Low-confidence cycles stay in the dataset and are shown in the dashboard, but are excluded from EUR and NPV totals.

## Key findings

- qi (peak rate) declines cycle-over-cycle in about 70% of wells, EUR in about 58%, checked both within-well and cross-sectionally.
- Negative-NPV share rises with cycle position (19.1% at cycle 1 up to 25.6% at cycle 3+), consistent with the degradation trend.
- Aggregate totals are skewed by a small number of standout wells; the top well was cross-checked directly against the raw Petrinex file to confirm it's real, not a fitting artifact.

## Limitations

- Petrinex's public API only goes back to 2022, so the 54-month window is a fraction of these wells' actual production history (Cold Lake has produced since the 1980s-90s, per public industry history, not this project's own data).
- Opex and steam cost are illustrative assumptions in `config.yaml`, not verified operator figures.
- The two batteries covered are a hardcoded constant (`TARGET_BATTERIES` in `data.py`), not a runtime parameter. Extending to another battery means editing that dict.
- Built for CSS thermal assets specifically; the cyclic assumption would not hold for conventional or SAGD wells without adaptation.
- IRR can return extreme, not-economically-meaningful values (thousands of percent) for cycles with a very small or front-loaded cost basis relative to revenue, since it's a root-finding solution over sparse monthly cash flows, not a bounded metric. NPV is the more reliable number in this dashboard; IRR is shown alongside it, not in place of it.

## Files

- [`app.py`](app.py): Streamlit dashboard (7 panels across 2 tabs)
- [`src/petro_decline/data.py`](src/petro_decline/data.py): Petrinex pull, filtering, injector identification
- [`src/petro_decline/decline.py`](src/petro_decline/decline.py): Arps curve fitting and model selection
- [`src/petro_decline/eur.py`](src/petro_decline/eur.py): EUR integration
- [`src/petro_decline/economics.py`](src/petro_decline/economics.py): NPV, IRR, live WTI pricing
- [`config.yaml`](config.yaml): sourced economic assumptions
- [`notebooks/detect_cycles_full.py`](notebooks/detect_cycles_full.py): full-scale cycle detection (feeds `decline.py`)
- `data/processed/`, `notebooks/output/`: pipeline outputs, committed so the dashboard runs without re-pulling data

## How to run

```bash
git clone https://github.com/jasonou216/Petro-decline-curve.git
cd Petro-decline-curve
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
# add a .env file with EIA_API_KEY=your-key-here (free at eia.gov/opendata)
# without it, the dashboard falls back to config.yaml's dated price
streamlit run app.py
```

## Tools

Python, pandas, numpy, scipy, Streamlit, Plotly, PyYAML, python-dotenv, Petrinex public API, EIA public API.

## Skills demonstrated

Time-series analysis • signal processing (peak detection) • nonlinear curve fitting • statistical model selection (AIC) • financial modeling (NPV, IRR, sensitivity analysis) • API integration • data pipeline design • interactive dashboard development • domain-specific problem framing (petroleum engineering)
