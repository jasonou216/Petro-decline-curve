# Known issues

A candid record of a technical review of this project: what it found, what got fixed as a
result, and what's staying as a documented limitation rather than a fix. Kept here instead
of only in a chat log because a reviewer catching real issues, and them getting addressed
or at least acknowledged, is more useful to show than pretending the first version was
already right.

## Fixed

1. **EUR and NPV were built from two different volumes.** `eur.cycle_eur` used to be a
   continuous integral of the fitted curve; `economics.cycle_cash_flows` built NPV from a
   discrete monthly sum of the same curve. For a declining curve those aren't the same
   number, the continuous integral is smaller, sometimes by a few percent, so a cycle's
   displayed EUR and the volume implied by its NPV didn't quite agree. `cycle_eur` now sums
   the identical monthly grid `cycle_cash_flows` uses, so the two numbers are the same
   volume, not two approximations of it. (`src/petro_decline/eur.py`,
   `src/petro_decline/economics.py`)
2. **Short cycles could force hyperbolic to "win" for the wrong reason.** With as few as 3
   data points, hyperbolic's 3 parameters had zero residual degrees of freedom, meaning it
   could pass through every point and post a near-perfect fit no matter what the data
   actually looked like, which drove AIC hugely negative and let it win structurally. That's
   exactly the bias AIC-over-R2 was supposed to prevent, just reappearing at small sample
   sizes. Switched to AICc (the small-sample-corrected form of AIC) and require at least 2
   residual degrees of freedom per model (`n >= k + 2`) before a model is even attempted.
   (`src/petro_decline/decline.py`)
3. **Shut-in months were treated as real decline observations.** `data.well_oil_series`
   zero-fills months Petrinex has no record for (soak phase, shut-in), and those zero
   months were passed straight into `curve_fit` as if they were genuine low-rate
   production, which could pull `qi`/`Di` off for any cycle with a mid-cycle interruption
   like a workover. Producing months only are used to fit the curve now; the cycle's full
   observed duration (and therefore EUR/NPV) is unchanged. (`src/petro_decline/decline.py`)
4. **Glossary contradicted the code.** The Harmonic entry claimed it "flattens out more
   than either other shape," but `b` is allowed up to 2.0 and a hyperbolic fit with `b > 1`
   flattens more than harmonic (`b = 1`) does. Reworded. (`app.py`)
5. **IRR could display a meaningless five- or six-digit percentage.** It's a root-finding
   solution over a handful of sparse monthly cash flows, not a bounded metric, so a cycle
   with a tiny or front-loaded cost basis could solve to a technically correct but useless
   number. Past 500% the dashboard now shows "not meaningful" instead of the raw figure.
   (`app.py`)

All three code fixes above changed the actual fitted results, so the full pipeline
(cycle fitting, EUR, economics) was re-run at full scale afterward, and every number in
the README and every dashboard screenshot reflects the corrected pipeline, not the
original run.

A follow-up pass, verifying the fixes above against the live dashboard, caught two
places the first round missed:

13. **The in-app Glossary still described the old EUR method** (a continuous integral,
    with the old `∫₀ᵀ q(t) dt` formula), which by then contradicted both the README and
    the actual code. Reworded to the discrete sum, matching everywhere else. (`app.py`)
14. **The Glossary's Confidence entry didn't mention the new low-confidence reason**
    (not enough producing months left to support a model, once shut-in months are
    dropped). Added. (`app.py`)

Also cleaned up two stale references to plain "AIC" (should read "AICc") left over in
`decline.py`'s module docstring and `fit_cycle`'s docstring after the AICc fix, and
moved a comment block that had gone stale (it described a `MIN_POINTS_TO_FIT` constant
that no longer exists, since the check moved into `_fit_single_model`) down to where the
actual logic lives.

## Documented, not fixed

6. **Petrinex's public monthly Files API 404s before 2022-01,** so the 54-month window
   this project pulls is a fraction of these wells' real production history (Cold Lake has
   produced since the 1980s-90s). Older data appears to exist through other Petrinex/AER
   channels (AER's product catalogue references conventional volumetric data back to
   2002), but this project didn't verify exactly what's free vs. request-only through
   those channels and didn't pursue pulling it. With an average of 1-1.75 high-confidence
   cycles per well, most wells here show one partial cycle inside this window, not a real
   multi-decade stack, so the degradation finding rests on a minority of wells with 2+
   visible cycles rather than deep per-well history. See README > Limitations.
7. **No diluent accounting on the revenue side.** WCS is priced directly against raw
   bitumen volume with a flat differential; a real bitumen netback separately nets out
   diluent (condensate) cost against a blended price. This project doesn't model that
   split, so netback, and everything downstream of it, is somewhat optimistic on top of
   opex and steam cost already being labeled illustrative rather than verified operator
   figures. See README > Limitations.
8. **Steam cost is a flat $200k per cycle** regardless of well size or actual steam
   volume, since real steam-volume data isn't available here. That makes "this cycle has
   negative NPV" close to a simple volume threshold (roughly 3,700 bbl at current prices)
   rather than a richer economic result, later cycles produce less, so more of them cross
   under that line. Stated explicitly in the README's Key findings now instead of left
   implicit in the number.
9. **Headline aggregates could read as an asset valuation.** "$1.5B total NPV" on its own
   invites the reading "these assets are worth $1.5B." It's the modelled NPV of the
   *observed* 2022-2026 cycles only, under this project's own illustrative cost
   assumptions, not a reserves or asset valuation. The README now labels it that way
   explicitly rather than presenting the bare number.
10. `curve_fit` is unweighted, so a cycle's early high-rate months dominate every fit more
    than its tail does, even though the tail is what EUR and late-cycle economics actually
    hinge on. Production is also treated as the instantaneous rate at each month's index,
    with no mid-month convention. Both are standard shortcuts for a quick DCA pass, this
    project doesn't claim otherwise, but they're worth knowing about.
11. `identify_injectors` flags a well as an injector if its OIL/BIT volume sums to
    approximately zero across the whole pulled window. A well that was steamed once and
    left in an extended soak for the entire 2022+ window would be misclassified the same
    way a real injector is. Probably rare, given how long that soak would have to last,
    but not spot-checked against the actual data.
12. `config.yaml`'s WCS differential and opex assumptions cite general ranges ("typical
    range midpoint per industry commentary") rather than one specific, dated, named source
    (AER, GLJ/Sproule, or a dated Reuters WCS-WTI print). Fine for an illustrative
    portfolio assumption, would need a real citation for anything more.
13. **EUR/NPV still project over a cycle's full duration, including shut-in months
    dropped from the fit.** The curve is fit only to actual producing months (see #3
    above), but EUR and NPV evaluate that fitted curve across the cycle's whole observed
    span, including whichever months were excluded from the fit itself. That's a
    deliberate "what the underlying decline trend implies over this window" choice, not
    an oversight, but it does mean a cycle with a real mid-cycle interruption gets
    modeled revenue for the months it was actually shut in, part of why total EUR moved
    after fix #3 went in.
14. **The two batteries have no meaningfully different pre-2022 history, so a "1st cycle"
    isn't always a real steam cycle.** For a well whose entire production history starts
    at the 2022 data horizon, what's left after the startup ramp is excluded still gets
    labeled "cycle 1", even when there was never a second steam job inside this window.
    It's initial-production decline wearing cycle terminology built for a genuine
    re-stimulation. This project's own top-NPV well came online mid-window and shows no
    re-steam pattern at all, its "cycle 1" boundary is a peak-detection artifact from
    ordinary noise. 581 of 1,190 wells with a usable fit (49%) have exactly one
    high-confidence cycle. The README now leads with the degradation finding (which
    rests on wells with a genuine 1st->2nd transition) rather than the dollar totals,
    and states this caveat directly in Key findings.
15. **No Crown royalty or abandonment/reclamation liability modeled.** Modelled NPV is
    pre-royalty gross-project cash flow. Alberta oil sands royalty runs roughly 1-9% of
    gross revenue pre-payout and 25-40% of net post-payout, not modeling it at all
    materially overstates every NPV figure here, on top of the diluent and cost-assumption
    caveats already listed. Added to README > Limitations as the most conspicuous
    omission for an upstream-Alberta audience.
16. **Currency wasn't stated anywhere.** All monetary figures (WTI, WCS, opex, steam
    cost, NPV) are USD; `config.yaml` and the dashboard didn't say so explicitly, and
    Alberta operating costs are normally quoted in CAD. Now stated in README >
    Limitations.
17. **The R2 >= 0.5 high-confidence threshold is a starting guess, not validated, and
    the totals are sensitive to it.** The top well above has R2 = 0.59, inside the
    lenient end of that band. Tightening to R2 >= 0.7 as a cross-check keeps 69.6% of
    cycles but only 67.3% of modelled NPV. Now stated in README > Limitations with the
    actual numbers.

Also fixed: `economics_full.py` and `cycle_degradation_comparison.py` had hardcoded
counts ("1,875 high-confidence cycles", "555 wells", "134 wells") left over from before
the AICc/zero-fill re-fit changed the actual numbers to 1,978 / 609 / 160,
`economics_full_report.txt` literally read "all 1,875" directly above a table that
summed to 1,978. The one that mattered (the printed report header) is now an f-string
off `len(econ)`; the two docstrings were reworded to not hardcode a number that the
next re-run could invalidate again. `DEVNOTES.md` claimed "every module has a
corresponding `tests/test_*.py`" when only a single `assert True` smoke test existed,
now genuinely true: `tests/test_data.py`, `test_decline.py`, `test_eur.py`, and
`test_economics.py` add 24 real tests (parameter recovery on synthetic Arps data, the
EUR/NPV consistency property directly, the zero-fill exclusion behavior, IRR/payback
edge cases). The dashboard's IRR display also now distinguishes "n/a (never negative)"
(cash flow profitable from month zero, common on the biggest wells) from "n/a (never
profitable)", instead of one bare "(n/a)" for both.

---

This came out of a line-by-line review checking the Arps forms, all three EUR closed-forms
(before they were replaced, see #1), the bbl/m3 conversion, and the monthly discount
convention against the actual code, plus clicking through the live dashboard.
