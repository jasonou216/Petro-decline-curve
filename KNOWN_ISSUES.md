# Known issues

Notes from going back over this project critically after the first version was working: what I caught and fixed, and what I'm leaving as a known limitation instead of pretending it's not there.

## Fixed

| # | Issue | Fix |
|---|---|---|
| 1 | `eur.cycle_eur` (continuous integral) and `economics.cycle_cash_flows` (discrete monthly sum) built NPV/EUR from different volumes for the same cycle | `cycle_eur` now sums the identical monthly grid `cycle_cash_flows` uses |
| 2 | With n=3 points, hyperbolic's 3 params had zero residual DOF, forcing a near-perfect fit and a structurally-winning AIC regardless of merit | Switched to AICc, require `n >= k+2` per model before it's attempted |
| 3 | `well_oil_series` zero-fills shut-in months, and those zeros were fit as real production, distorting qi/Di | Fit uses producing months only; EUR/NPV still span the full cycle duration |
| 4 | Glossary said harmonic "flattens more than either other shape" (false once b>1 hyperbolic is allowed); EUR and Confidence entries were stale | Reworded |
| 5 | IRR could display a meaningless 5-6 digit percentage; `(n/a)` didn't say whether cash flow was never negative or never profitable | Capped at ">500%, not meaningful"; n/a now says which |
| 6 | Hardcoded counts in two notebook scripts went stale after re-fits; `economics_full_report.txt` contradicted its own table | Report header is an f-string off `len(econ)`; docstrings no longer hardcode counts |
| 7 | `DEVNOTES.md` claimed full test coverage; only a smoke test existed | Real tests for every module in `src/petro_decline/` |
| 8 | README said the 581 single-cycle wells were "mostly Nabiye" (backwards, 88% Mahihkan); NPV mean/median had no unit; "live EIA price" implied more than a flat single-day quote; near-miss review wording read as 60% of *accepted* cycles | Corrected in the README |
| 9 | `well_oil_series` filtered `OIL` only while `identify_injectors` screens `OIL`/`BIT` | Both use the same set (no-op on this data, confirmed by diffing regenerated output) |
| 10 | No `LICENSE`; Windows-only venv command; EUR/NPV metric cards clipped at normal widths; Petrinex redistribution terms unchecked | MIT `LICENSE`; Mac/Linux command; compact `$1.03B` / `4.08M m3` cards; terms checked, non-commercial use permitted, Crown copyright acknowledged |
| 11 | 21 Nabiye wells that started producing in May-Aug 2024 at 3,500-7,500 m3/month with no shut-in (SA-SAGD-like, no steam cycles) were fit as CSS: 7 of the 12 highest-NPV wells, 34% of Nabiye's NPV | `wells.py` flags continuous-process wells and leaves them out |
| 12 | 184 Mahihkan wells first reported in May 2026 (battery rate +16% that month) counted as "wells analyzed" with two months of data | Wells under 6 months of history are left out |
| 13 | A plant shutdown (Nabiye, Aug-Nov 2023) made every well dip and recover together, producing a wave of false cycle starts (67 in Nov 2023 vs a median of 27) | `outages.py` finds battery-wide dips; those months are interpolated for detection and dropped from fits |
| 14 | Steam cost was charged in the first production month although injection and soak keep a well off for 1-3 months | `steam_lead_months` (2, from the AER filings), cash flow starts at the spend |
| 15 | Cycle detection lived only in notebooks, with no tests | Moved to `src/petro_decline/cycles.py` with tests; regenerated output was identical |
| 16 | Nothing showed the main finding survives other ways of cutting cycles | `sensitivity_checks.py` reruns detection under five settings and splits the finding by well group |
| 17 | Cycle numbers read as lifetime numbers; the dashboard didn't say which wells were left out | Glossary and README say cycles count from Jan 2022; `NewInWindow` flag; overview lists exclusions |
| 18 | Sidetracks and redrills (well ID event suffix not 00) weren't flagged | `IsRedrill` flag; main finding unchanged without them |
| 19 | Petrinex volumes had never been compared with the operator's own figures | `validate_against_filings.py`: 0-5% difference for 2023-24 |

The detection and economics changes moved every headline number, so the pipeline was rerun in full. WTI is now $96.24 (6 Oct 2026), up from $83.90, which lifts NPV on its own.

## Documented, not fixed

| # | Issue | Where it's noted |
|---|---|---|
| 1 | Petrinex's Files API 404s before 2022-01; older data may exist elsewhere, not pursued | README > Limitations |
| 2 | Detected "cycles" are decline segments, not confirmed steam jobs: median 8 months vs multi-year late cycles in the filings, 13-24% follow a zero month. Wider spacing and a steam-gap rule both kept the finding and neither raised the share of trusted fits, so no cut is clearly better without real steam dates | README > Limitations |
| 3 | LASER co-injection (~19 Mahihkan pads) and infill wells aren't modelled, no well-to-pad mapping | README > Limitations |
| 4 | Only 11 wells that started inside the window have a 1st-to-2nd cycle transition (qi down in 64%, recovery in 45%), too few to say anything about true early cycles | README > Key findings |
| 5 | The SA-SAGD identification is inferred (timing, rate, location, and 662k vs 584k m3 for the S01 pad), the filings list no well IDs | README > Key findings |
| 6 | The May 2026 Mahihkan well jump is assumed to be a reporting change, not confirmed | README > Limitations |
| 7 | Outage detection is data-driven; the 2022-operating-year filing is missing, Nabiye 2026-05 and Mahihkan 2022-02 are flagged without corroboration | README > Limitations |
| 8 | Steam cost is a flat $200k/cycle; negative-NPV share runs 2-26% across $50k-$300k and its rise with cycle position only shows at $200k+. The filings' steam-oil ratios imply ~$26/m3 of steam at $200k, probably conservative | README > Key findings |
| 9 | Per-cycle economics vs pad-level shared costs: the operator keeps steaming pads this model would call 17% negative | README > Limitations |
| 10 | No diluent accounting, WCS priced against raw bitumen | README > Limitations |
| 11 | No Crown royalty or abandonment/reclamation liability | README > Limitations |
| 12 | `curve_fit` unweighted; no mid-month convention | README > Limitations |
| 13 | `identify_injectors` could misclassify a well in an extended soak for the whole window | not spot-checked, likely rare |
| 14 | `config.yaml`'s differential/opex cite general ranges, not one dated source | acceptable for an illustrative assumption |
| 15 | EUR/NPV still project across shut-in and outage months excluded from the fit | README > Methodology notes |
| 16 | USD stated, no CAD conversion; nominal 10% discount rate applied to flat cash flows | README > Limitations |
| 17 | R2 >= 0.5 threshold isn't validated (0.7 keeps 69% of cycles and 70% of NPV) | README > Limitations |

---

Found by going back through the Arps forms, EUR math, bbl/m3 conversion, discount convention, cycle-detection assumptions and well selection line by line against the actual code, the raw Petrinex data and Imperial's AER filings, and clicking through the live dashboard myself.
