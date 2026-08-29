# Project notes

Working notes on how this project is organized, mostly for my own reference when
I come back to it (e.g. before an interview) and don't remember why something is
built the way it is.

## Context

The project pulls Alberta well production data from Petrinex, detects individual
production cycles per well, fits Arps decline curves to each cycle, calculates EUR,
layers on NPV/IRR economics, and presents it all in a Streamlit dashboard, for two
Cold Lake CSS batteries: Mahihkan 02-21 (`ABBT0051212`) and Nabiye 11-23
(`ABBT0119087`) (see `TARGET_BATTERIES` in `data.py`).

**Cold Lake is a CSS (Cyclic Steam Stimulation) thermal asset, not a conventional
play.** Wells cycle through steam/soak/produce phases repeatedly, so they don't
follow a standard Arps decline continuously. I tried well-level and pad-level
(summed across a battery) fitting first and rejected both once I actually plotted
the data, wells cycle in a sawtooth rather than declining smoothly, and pad-level
aggregation just hid the cycling rather than averaging it out. The methodology
that actually matches the data: detect each steam-soak-produce cycle per well, and
fit Arps to each cycle independently.

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

No linter/formatter configured yet, if I add one (ruff, black), update this section.

## Architecture

Source lives under `src/petro_decline/` (src-layout, installed editable via
`pyproject.toml`, so `import petro_decline` works from tests, notebooks, and
`app.py` without path hacks).

1. **`data.py`**: pulls raw well production records from Petrinex and cleans them
   into a per-well monthly production DataFrame. Only module that knows about
   Petrinex's API/file format, everything downstream works with clean DataFrames.
   Each monthly Petrinex file is a ~120MB province-wide dump, double-zipped;
   `load_and_filter_month` downloads and filters it entirely in memory and never
   writes the full file to disk, only the small filtered result goes to
   `data/processed/monthly/{year_month}_filtered.csv`, which doubles as the resume
   checkpoint for `pull_range`. Filters to `ActivityID == 'PROD'` and
   `FromToIDType == 'WI'`; `identify_injectors` flags wells with zero/near-zero
   OIL/BIT volume across the full pulled history, including wells with no OIL/BIT
   rows at all (a well absent from that product entirely still counts as zero, not
   excluded). Run as `python -m petro_decline.data --start YYYY-MM --end YYYY-MM`.
   The public Files API only serves months from 2022-01 onward, earlier months
   404, confirmed by probing back to 2016-06, so `--start` defaults to `2022-01`.
2. **Cycle detection** (`notebooks/explore_cycle_detection.py`,
   `notebooks/detect_cycles_full.py`): peak detection on each well's monthly oil,
   using relative/local prominence rather than a global max so later, weaker
   cycles still register, plus a minimum-spacing rule, a minimum-volume filter,
   and startup-ramp exclusion. Not in `data.py`, it lives in notebooks since it
   was validated there first. Outputs `notebooks/output/cycles_full.csv`, which
   `decline.py` and `app.py` both read.
3. **`decline.py`**: fits Arps decline models (exponential, hyperbolic, harmonic)
   to each cycle independently and picks the best by AIC, not R2 (hyperbolic's
   extra parameter almost always wins on raw R2 whether or not it's earning its
   keep). Flags a fit `low_confidence` if the cycle is too short, R2 is poor, or a
   parameter hits its bound.
4. **`eur.py`**: integrates a fitted decline curve over the cycle's own observed
   duration (not out to an economic limit) to get an Estimated Ultimate Recovery.
5. **`economics.py`**: per-cycle NPV/IRR/payback from monthly production, live WTI
   price from the EIA API with a documented `config.yaml` fallback, rolled up per
   well.

`app.py` at the repo root is the Streamlit entry point, imports from
`petro_decline` and stays thin (UI/layout + calls into the modules above), no
analysis logic in it directly.

`data/raw/` exists but is unused by the pipeline (province-wide downloads are
filtered in memory, never written there); `data/processed/` holds monthly
checkpoints and per-battery well-level output, both gitignored except the two
well-level CSVs `app.py` actually reads at runtime (needed for the dashboard to
work when deployed, not just locally). `notebooks/` is for exploratory analysis,
once logic is validated there I move it into `src/petro_decline/` and cover it
with a test rather than leaving it notebook-only.

## Coding conventions

- Type hints on all function signatures.
- Docstrings on all public functions (purpose, parameters, what's returned), this
  is a portfolio piece I need to be able to walk an interviewer through.
- Keep functions small and independently testable (curve-fitting math separate
  from data loading separate from plotting) rather than large end-to-end functions.
- Every module in `src/petro_decline/` has a corresponding `tests/test_*.py`.
