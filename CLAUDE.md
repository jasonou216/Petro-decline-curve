# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Portfolio project for a 2nd-year Chemical Engineering student (Petroleum minor) applying
to upstream O&G internships. The author knows Python and has some process-engineering
(HYSYS) background but is not a professional developer, and wants to be able to explain
every part of this codebase in an interview. **Favor clear, readable code over clever
code.** When a code choice is non-obvious (e.g. why a particular Arps form, a numerical
stability trick in curve fitting, a discounting convention in the economics layer),
explain the *why* in a comment — don't leave the reasoning implicit.

The project pulls Alberta well production data from Petrinex, fits Arps decline curves,
calculates EUR, builds a type curve for the **Cold Lake** play, layers on basic
NPV/IRR economics, and presents everything in a Streamlit dashboard.

**Cold Lake is a CSS (Cyclic Steam Stimulation) thermal asset, not a conventional
play.** Individual wells cycle through steam/soak/produce phases, so they don't follow
a standard Arps decline at the well level. The methodology instead aggregates
PROD-activity volumes across all producing wells at the battery/pad level per month
(summed, injectors excluded), and fits Arps decline to that pad-level aggregate time
series rather than to individual wells. Two batteries are pulled as a comparison pair:
Mahihkan 02-21 (`ABBT0051212`, primary) and Nabiye 11-23 (`ABBT0119087`, secondary) —
see `TARGET_BATTERIES` in `data.py`.

## Commands

```bash
# Activate the environment (Windows)
.venv\Scripts\activate

# Install/update dependencies
pip install -r requirements.txt
pip install -e .

# Run the dashboard
streamlit run app.py

# Run all tests
pytest

# Run a single test file / test
pytest tests/test_decline.py
pytest tests/test_decline.py::test_hyperbolic_fit -v
```

There is no linter or formatter configured yet — if one is added (e.g. `ruff`, `black`),
update this section.

## Architecture

Source lives under `src/petro_decline/` (src-layout, installed editable via
`pyproject.toml` so `import petro_decline` works from tests, notebooks, and `app.py`
without path hacks). The pipeline is a straight-line data flow through four modules:

1. **`data.py`** — pulls raw well production records from Petrinex and cleans them into
   a per-well monthly production DataFrame. This is the only module that should know
   about Petrinex's API/file format; everything downstream works with clean DataFrames.
   Each monthly Petrinex file is a ~120MB province-wide dump double-zipped by the API
   (outer zip containing an inner zip containing the CSV); `load_and_filter_month`
   downloads and filters it entirely in memory and never writes the full file to disk
   — only the small, already-filtered result is written, to
   `data/processed/monthly/{year_month}_filtered.csv`, which also serves as the resume
   checkpoint for `pull_range`. Filters to `ActivityID == 'PROD'` and
   `FromToIDType == 'WI'`; `identify_injectors` flags wells whose OIL/BIT volume is
   zero/near-zero across the full pulled history (including wells with *no* OIL/BIT
   rows at all — a well absent from that product entirely still counts as zero, it's
   not excluded from consideration) before `aggregate_pad_production` sums producing
   wells to the pad/battery level for `decline.py`. Run as
   `python -m petro_decline.data --start YYYY-MM --end YYYY-MM`. **The public Files
   API only serves months from 2022-01 onward** — earlier months 404 with
   `{"Message":"Requested resource doesn't exist."}` (confirmed by probing back to
   2016-06); `--start` defaults to `2022-01` accordingly. Full pre-2022 history would
   need a different Petrinex source.
2. **`decline.py`** — fits Arps decline models (exponential, hyperbolic, harmonic) to a
   production time series and returns fitted parameters (qi, Di, b). Takes a
   `methodology` (well-level vs. pad-level aggregate) so the fit target is explicit and
   the module can be extended later — currently only pad-level aggregate fitting is
   implemented, since Cold Lake's CSS cycling makes well-level Arps fits invalid.
3. **`eur.py`** — integrates a fitted decline curve out to an economic limit / time cutoff
   to produce an Estimated Ultimate Recovery. Depends on `decline.py`'s fitted output.
4. **`economics.py`** — takes a production forecast (single well or aggregated type
   curve) and applies pricing/cost assumptions to compute NPV and IRR.

`app.py` at the repo root is the Streamlit entry point; it imports from `petro_decline`
and should stay thin (UI/layout + calls into the modules above) rather than holding
analysis logic itself.

`data/raw/` exists but is currently unused by the pipeline (province-wide downloads are
filtered in memory and never written there); `data/processed/` holds monthly
checkpoints and per-battery well-level/pad-level output. Both are gitignored — only
`.gitkeep` placeholders are tracked. `notebooks/` is for exploratory analysis; once
logic is validated there, move it into `src/petro_decline/` and cover it with a test
rather than leaving it notebook-only.

## Coding conventions

- Type hints on all function signatures.
- Docstrings on all public functions (purpose, parameters, what's returned) — this is
  a portfolio piece the author needs to walk an interviewer through.
- Keep functions small and independently testable (e.g. curve-fitting math separate from
  data loading separate from plotting) rather than large end-to-end functions.
- Every module in `src/petro_decline/` should have a corresponding `tests/test_*.py`.
