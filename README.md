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

| Battery | Operator | Wells analyzed | High-confidence cycles | Avg. HC cycles/well | Modelled EUR (m3) | Modelled NPV | Wells w/ negative NPV | Cycles w/ negative NPV |
|---|---|---|---|---|---|---|---|---|
| Mahihkan Battery 02-21 | Imperial Oil | 1,457 | 1,485 | 1.02 | 4,083,003 | $1,029,957,347 | 18.2% (of 946) | 23.1% |
| Nabiye 11-23 | Imperial Oil | 281 | 493 | 1.75 | 1,966,050 | $546,457,764 | 11.9% (of 244) | 17.2% |

Combined: 69.6% of all fitted cycles are low confidence, 21.6% of high-confidence cycles carry negative NPV, and modelled NPV across both batteries is $1,576,415,111 (mean cycle NPV $797k, median $315k, one well alone accounting for $40.2M). "Modelled NPV" is the sum of the observed 2022-2026 cycles under this project's cost assumptions, it's not an asset valuation or a reserves estimate. EUR and production volumes are in m3, the unit Petrinex reports in. "Avg. HC cycles/well" is out of *every* well analyzed, including the majority that have zero or one high-confidence cycle in this window, not just wells with several, see Limitations.

## Theory

Arps decline: `q(t) = qi / (1 + b * Di * t)^(1/b)`, fit per cycle in three forms (exponential b=0, harmonic b=1, hyperbolic general form) on the cycle's actual producing months only, shut-in/soak gaps within a cycle are dropped before fitting rather than treated as zero-rate observations. The winner is chosen **by AICc, not R2**: hyperbolic's extra free parameter almost always improves raw R2 whether or not it's earning its keep, and AICc, the small-sample-corrected form of AIC, penalizes that properly even when a cycle only has a handful of points (plain AIC is itself biased in that regime). Each form is only attempted with at least 2 residual degrees of freedom.

Per-cycle recovery, called "EUR" throughout the dashboard: `EUR = sum over t=0..T-1 of q(t)`, where T is the cycle's own observed duration in months, not an economic limit. It's really cumulative production over the cycle's observed window, for a non-final cycle that's close to the well's actual produced volume rather than a forward-looking estimate. It's summed on the same monthly grid as NPV below, not integrated continuously, so the two numbers are built from the same volume rather than two different approximations of it.

NPV, per cycle: `NPV = sum over t of [ q_t * (price - opex) / (1 + r)^t ] - steam_cost`. Price is the WCS netback (WTI minus a differential), pulled live from the EIA public API with a documented fallback in `config.yaml`. `q_t` is the same monthly value EUR sums.

## Methodology notes

- **Cycle detection**: peak detection on monthly oil, with relative/local prominence (a peak must clear its own preceding trough by a threshold, not the well's all-time max), a minimum 4-month spacing between cycles, and a minimum-volume filter to drop wells too small to have a meaningful signal. A well's first rise from zero is tagged as startup, not a cycle. The 40% prominence threshold was checked, not assumed: 25 random borderline (30-40%) candidates were judged by eye, and about 60% turned out to be noise, which confirmed the cutoff.
- **Confidence flagging**: a fit is low confidence if the cycle is too short, R2 is poor, a parameter hits its bound, or there weren't enough producing months to support the model it picked. Most of the 69.6% low-confidence rate comes from real production being non-monotonic within a cycle (a rise, a dip, another bump) while Arps curves are strictly monotonic. Low-confidence cycles stay in the dataset and are shown in the dashboard, but are excluded from EUR and NPV totals.
- **Shut-in months are dropped from fitting, not from EUR/NPV.** The curve is fit only to a cycle's actual producing months, but EUR and NPV still project the fitted curve across the cycle's *full* observed duration, including whatever shut-in months were excluded from the fit. That's a deliberate "what the underlying decline trend implies over this window" choice, not an oversight, but it does mean a cycle with a real mid-cycle interruption gets modeled revenue for those months rather than the true zero it actually produced then.

## Key findings

- qi (peak rate) declines cycle-over-cycle in about 70% of wells, per-cycle recovery in about 60%, checked both within-well (across the 609 wells with at least a 1st and 2nd high-confidence cycle) and cross-sectionally.
- Negative-NPV share rises with cycle position (17.5% at cycle 1 up to 25.2% at cycle 3+), consistent with the degradation trend. That said, this is a largely mechanical result: steam cost is a flat $200k per cycle regardless of well size, so at current prices "negative NPV" is close to "this cycle produced under ~3,700 bbl", later cycles produce less, so more of them fall under that line. Worth stating plainly so it doesn't read as a richer finding than it is.
- Modelled totals are skewed by a small number of standout wells, not evenly distributed across the ~1,190 wells with a usable fit; the top well was cross-checked directly against the raw Petrinex file to confirm it's real, not a fitting artifact.

## Limitations

- Petrinex's monthly Files API (`publicdata/API/Files/AB/Vol/...`, what this pipeline pulls from) 404s for anything before 2022-01, so the 54-month window is a fraction of these wells' actual production history, Cold Lake has produced since the 1980s-90s. Older data appears to exist through other Petrinex/AER channels (AER's product catalogue references conventional volumetric data back to 2002), but this project didn't verify exactly what's free vs. request-only through those channels, and didn't pursue pulling it. With 1.02-1.75 high-confidence cycles per well on average, most wells here show one partial cycle, not a real multi-decade stack, so the degradation finding rests on a minority of wells that happen to show 2+ cycles in this window rather than deep per-well history.
- Revenue is priced as raw bitumen volume at the WCS blended price with only a flat differential. WCS is a diluted-bitumen blend (roughly 25-30% condensate); a real bitumen netback nets out diluent cost separately. This project doesn't model that, so netback (and everything downstream of it) is optimistic to some degree, on top of opex and steam cost already being illustrative, not verified operator figures.
- The two batteries covered are a hardcoded constant (`TARGET_BATTERIES` in `data.py`), not a runtime parameter. Extending to another battery means editing that dict.
- Built for CSS thermal assets specifically; the cyclic assumption would not hold for conventional or SAGD wells without adaptation.
- IRR can return extreme, not-economically-meaningful values (thousands of percent) for cycles with a very small or front-loaded cost basis relative to revenue, since it's a root-finding solution over sparse monthly cash flows, not a bounded metric. NPV is the more reliable number in this dashboard; IRR is shown alongside it, not in place of it.
- Production is treated as the instantaneous monthly rate at each month's index, standard for a quick DCA pass but not a mid-month convention. Curve fitting is also unweighted, so the high-rate early months of a cycle dominate every fit more than the (economically important) tail does.

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
