# Project notes

Working notes on how this project is organized, mostly for my own reference (e.g. before an interview).

## Context

Pulls Alberta well production data from Petrinex, detects individual production cycles per well, fits Arps decline curves to each cycle, calculates EUR, layers on NPV/IRR economics, presents it all in a Streamlit dashboard. Two Cold Lake CSS batteries: Mahihkan 02-21 (`ABBT0051212`) and Nabiye 11-23 (`ABBT0119087`), see `TARGET_BATTERIES` in `data.py`.

**Cold Lake is a CSS (Cyclic Steam Stimulation) thermal asset, not a conventional play.** Wells cycle through steam/soak/produce repeatedly, no standard continuous Arps decline. Well-level and pad-level (summed across a battery) fitting were both tried and rejected once plotted, wells sawtooth rather than decline smoothly, and pad-level aggregation just hides the cycling. What matches the data: detect each steam-soak-produce cycle per well, fit Arps to each cycle independently.

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

Source lives under `src/petro_decline/` (src-layout, installed editable via `pyproject.toml`, so `import petro_decline` works from tests, notebooks, and `app.py` without path hacks).

1. **`data.py`**: pulls raw Petrinex records, cleans into per-well monthly production. Only module that knows Petrinex's API/file format. Each monthly file is a ~120MB province-wide dump, double-zipped; `load_and_filter_month` filters entirely in memory, never writes the full file to disk, only the small filtered result (`data/processed/monthly/{year_month}_filtered.csv`, doubles as the resume checkpoint). Filters to `ActivityID == 'PROD'`, `FromToIDType == 'WI'`; `identify_injectors` flags zero/near-zero OIL/BIT wells, including wells with no OIL/BIT rows at all. Public Files API only serves 2022-01 onward, so `--start` defaults there.
2. **Cycle detection** (`notebooks/explore_cycle_detection.py`, `notebooks/detect_cycles_full.py`): peak detection using relative/local prominence (not a global max, so later/weaker cycles still register), minimum spacing, minimum-volume filter, startup-ramp exclusion. Lives in notebooks, not `data.py`, since it was validated there first. Outputs `notebooks/output/cycles_full.csv`, read by `decline.py` and `app.py`.
3. **`decline.py`**: fits exponential/hyperbolic/harmonic per cycle, picks the best by AICc (not raw R2 or plain AIC, both biased toward hyperbolic's extra parameter, especially at small n). Flags `low_confidence` if too short, poor R2, or a parameter pinned at its bound.
4. **`eur.py`**: sums a fitted curve's monthly predicted volume over the cycle's own duration (not an economic limit).
5. **`economics.py`**: per-cycle NPV/IRR/payback from monthly production, live WTI (EIA API, `config.yaml` fallback), rolled up per well.

`app.py` is the Streamlit entry point, thin UI/layout only, no analysis logic.

`data/raw/` is unused (downloads filtered in memory, never written there); `data/processed/` holds checkpoints and per-battery well-level output, gitignored except the two CSVs `app.py` reads at runtime. `notebooks/` is for exploratory analysis, once validated it moves into `src/petro_decline/` with a test.

## Coding conventions

- Type hints on all function signatures.
- Docstrings on all public functions, this is a portfolio piece I need to walk an interviewer through.
- Small, independently testable functions (curve-fitting math separate from data loading separate from plotting).
- Every module in `src/petro_decline/` has a corresponding `tests/test_*.py`.
