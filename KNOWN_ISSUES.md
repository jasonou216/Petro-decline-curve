# Known issues

A candid record of technical reviews of this project: what got fixed, and what's staying as a documented limitation. Kept here instead of buried in chat history.

## Fixed

| # | Issue | Fix |
|---|---|---|
| 1 | `eur.cycle_eur` (continuous integral) and `economics.cycle_cash_flows` (discrete monthly sum) built NPV/EUR from different volumes for the same cycle | `cycle_eur` now sums the identical monthly grid `cycle_cash_flows` uses |
| 2 | With n=3 points, hyperbolic's 3 params had zero residual DOF, forcing a near-perfect fit and a structurally-winning AIC regardless of merit | Switched to AICc, require `n >= k+2` per model before it's attempted |
| 3 | `well_oil_series` zero-fills shut-in months, and those zeros were fit as real production, distorting qi/Di | Fit uses producing months only; EUR/NPV still span the full cycle duration |
| 4 | Glossary said harmonic "flattens more than either other shape" (false once b>1 hyperbolic is allowed) | Reworded |
| 5 | IRR could display a meaningless 5-6 digit percentage | Capped display: ">500%, not meaningful" |
| 6 | Glossary's EUR entry still described the old continuous-integral method | Reworded to match the discrete-sum code |
| 7 | Glossary's Confidence entry missed the new "not enough producing months" reason | Added |
| 8 | Stale "AIC" wording and a dangling comment left over in `decline.py` after the AICc fix | Fixed wording; moved comment to where the logic lives |
| 9 | Hardcoded cycle/well counts in `economics_full.py` / `cycle_degradation_comparison.py` went stale after the re-fit (1,875 → 1,978, 555 → 609, 134 → 160); `economics_full_report.txt` contradicted its own table | Report header is now an f-string off `len(econ)`; docstrings reworded; report regenerated |
| 10 | `DEVNOTES.md` claimed full test coverage; only a trivial smoke test existed | Added 24 real tests across `test_data.py`, `test_decline.py`, `test_eur.py`, `test_economics.py` |
| 11 | IRR `(n/a)` didn't distinguish "cash flow never negative" (good sign) from "never profitable" (bad) | Dashboard now shows which |
| 24 | README said 581 single-HC-cycle wells were "mostly Nabiye" | Backwards: 513/581 (88%) are Mahihkan. Fixed |
| 25 | "mean $797k, median $315k" NPV had no unit, read as per-well | Labeled per cycle; per-well is $1.32M/$575k |
| 26 | "live from the EIA API" implied more than a single day's flat spot price with no forward curve | One sentence added in Theory |
| 27 | 25-sample near-miss review wording ("~60% were noise, confirming the cutoff") read as 60% of *accepted* cycles | Clarified: 60% of *rejected* candidates |
| 28 | `well_oil_series` filtered `ProductID == "OIL"` only; `identify_injectors` screens `{"OIL","BIT"}` | `well_oil_series` now sums the same set. Zero BIT rows in either battery, confirmed no-op (`git diff` on regenerated `cycles_full.csv` is empty) |
| 29 | Flagship "recovery drops cycle-over-cycle" finding and the "cycle 1 isn't always real" caveat sat in separate bullets, never connected | Addressed head-on in the same bullet |
| 30 | No `LICENSE`; "How to run" only showed Windows activation | Added MIT `LICENSE`; added the Mac/Linux command |

All fixes to `decline.py`/`eur.py` changed real fitted results, so the full pipeline was re-run at full scale afterward, every number in the README and every screenshot reflects the corrected run.

## Documented, not fixed

| # | Issue | Where it's noted |
|---|---|---|
| 12 | Petrinex's Files API 404s before 2022-01; older data may exist via other Petrinex/AER channels, not verified or pursued | README > Limitations |
| 13 | No diluent accounting, WCS priced against raw bitumen volume | README > Limitations |
| 14 | Steam cost is a flat $200k/cycle, so "negative NPV" is close to "produced under ~3,700 bbl" | README > Key findings |
| 15 | Headline NPV/EUR totals could read as an asset valuation | README > Key findings |
| 16 | `curve_fit` is unweighted (early months dominate the fit); no mid-month convention | README > Limitations |
| 17 | `identify_injectors` could misclassify a well in an extended soak for the whole window as an injector | not spot-checked, likely rare |
| 18 | `config.yaml`'s differential/opex cite general ranges, not one dated source | acceptable for an illustrative assumption |
| 19 | EUR/NPV still project across shut-in months that were excluded from the fit itself | README > Methodology notes |
| 20 | "Cycle 1" isn't always a real steam cycle for a well with no pre-2022 history, top-NPV well example, 581/1,190 wells have exactly one HC cycle | README > Key findings |
| 21 | No Crown royalty or abandonment/reclamation liability modeled, understates cost materially | README > Limitations |
| 22 | Currency (USD) wasn't stated anywhere | README > Limitations |
| 23 | R2 >= 0.5 threshold isn't validated; 67.3% of NPV survives at R2 >= 0.7 | README > Limitations |
| 31 | 10% discount rate is nominal, applied to flat/non-escalating cash flows, understates true NPV | README > Limitations |
| 32 | Steam cost charged same month as peak production (t=0), no lag for the real steam-soak period | README > Limitations |
| 33 | Dashboard metric cards may clip at narrow (tablet/laptop) widths; `st.metric` has no overflow handling | not pixel-verified live, code has no width/wrap handling either way |
| 34 | Petrinex's redistribution terms for the committed filtered CSVs weren't confirmed | unresolved, needs a manual check of Petrinex/AER's actual terms of use |

---

Came out of line-by-line reviews checking the Arps forms, EUR math, bbl/m3 conversion, discount convention, and cycle-detection assumptions against the actual code and raw Petrinex data, plus clicking through the live dashboard.
