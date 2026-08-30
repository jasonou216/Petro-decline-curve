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

## Documented, not fixed

6. **Petrinex's public monthly Files API only serves 2022 onward,** so the 54-month window
   this project pulls is a fraction of these wells' real production history (Cold Lake has
   produced since the 1980s-90s). AER's own product catalogue lists conventional
   volumetric data back to 2002 through a separate channel, but free self-service only
   covers the most recent 4 years, older periods need a compilation/purchase request that
   this project hasn't pursued. With an average of 1-1.75 high-confidence cycles per well,
   most wells here show one partial cycle inside this window, not a real multi-decade
   stack, so the degradation finding rests on a minority of wells with 2+ visible cycles
   rather than deep per-well history. See README > Limitations.
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

---

This came out of a line-by-line review checking the Arps forms, all three EUR closed-forms
(before they were replaced, see #1), the bbl/m3 conversion, and the monthly discount
convention against the actual code, plus clicking through the live dashboard.
