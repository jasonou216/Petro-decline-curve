# Petro Decline Curves

Portfolio project analyzing Alberta well production data to build a decline-curve
type curve and economics model, presented as a Streamlit dashboard.

Built as part of internship applications for upstream oil & gas roles.

## What it does

1. Pulls monthly production data from [Petrinex](https://www.petrinex.gov.ab.ca/) for
   two Cold Lake CSS batteries — Mahihkan 02-21 (`ABBT0051212`) and Nabiye 11-23
   (`ABBT0119087`) — and identifies injector vs. producer wells
   (`src/petro_decline/data.py`).
2. Detects individual production *cycles* within each producer well (steam
   stimulation → decline → next stimulation) and fits Arps decline
   (exponential, hyperbolic, harmonic) to each cycle independently — pad-level
   and whole-well fitting were both tried and rejected; see Methodology below
   and `src/petro_decline/decline.py`.
3. Calculates per-cycle Estimated Ultimate Recovery (EUR) from the fitted curves.
4. Compares Mahihkan and Nabiye, and compares cycles within/across wells, as a
   type-curve pair for the **Cold Lake** play.
5. Applies a per-cycle economics layer (NPV, IRR, payback, rolled up per well)
   using live WTI pricing and documented, sourced assumptions
   (`src/petro_decline/economics.py`, `config.yaml`).
6. Presents the results in an interactive Streamlit dashboard.

## Project structure

```
petro-decline-curves/
├── app.py                    # Streamlit dashboard entry point
├── config.yaml                # economics.py assumptions (value/source/last_updated each)
├── .env                        # EIA_API_KEY (gitignored, not committed)
├── src/petro_decline/
│   ├── data.py                # Petrinex data pull + cleaning
│   ├── decline.py             # Arps decline curve models + fitting
│   ├── eur.py                 # EUR calculation
│   └── economics.py           # NPV / IRR / payback, live WTI + config.yaml
├── data/
│   ├── raw/                   # unused by the pipeline — province-wide Petrinex
│   │                          # downloads are filtered entirely in memory and
│   │                          # never written here (gitignored)
│   └── processed/              # per-month checkpoints + well-level/pad-level
│                                # output per battery (gitignored)
├── notebooks/                 # Exploratory analysis
├── tests/                     # pytest unit tests
└── requirements.txt
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
pip install -e .              # makes `petro_decline` importable from src/
```

For `economics.py`'s live WTI price, create a `.env` file at the project root
(gitignored) with:

```
EIA_API_KEY=your-key-here
```

Get a free key at https://www.eia.gov/opendata/register.php. Without it,
`economics.load_assumptions()` prints a warning and falls back to the
`wti_price_fallback` value in `config.yaml` — it won't crash.

## Pulling data

```bash
# defaults to 2022-01 (earliest month the public Files API serves) through the
# current month; resumable via data/processed/monthly/ checkpoints
python -m petro_decline.data --start 2022-01 --end 2026-06
```

Writes, per battery, `<battery>_well_level.csv` (every well, tagged `IsInjector`) and
`<battery>_pad_level.csv` (producing wells only, summed per product per month) to
`data/processed/`, plus `injector_wells.csv` listing flagged injector wells.

## Methodology & Limitations

- **Injector reporting differs by operator.** Mahihkan's operator co-reports some
  injector wells within the battery's own PROD roster (water-only, zero oil/bitumen —
  31 such wells identified and excluded from the producer aggregate); Nabiye's
  operator reports all injectors under a separate injection facility ID entirely
  (`ABIF0119086`, out of scope for this pipeline), so no equivalent wells appear in
  its PROD roster. Both patterns are handled correctly by the `ActivityID == 'PROD'`
  filter, but it's a reminder that operator reporting conventions vary even within
  the same asset type — a well count or injector count isn't directly comparable
  across batteries without checking how each operator reports.

- **Economics (Phase 5) skew heavily toward a small number of exceptionally
  high-rate wells.** Across all 1,875 high-confidence cycles at live pricing
  (WTI ~$86/bbl), median cycle NPV is **$307k**, but **22.8% of cycles and
  18.0% of wells show negative NPV** at current prices — the ~$1.55B
  portfolio total is not evenly distributed; one verified Nabiye well
  (`ABWI105110806603W400`) alone contributes **$42.1M** of it. Negative-NPV
  share also rises with cycle position (19.1% at 1st → 25.6% at 3rd+),
  consistent with the Phase 4 finding that later cycles recover less oil —
  the economics and degradation results agree, not coincidentally.

## Running

```bash
streamlit run app.py
```

## Testing

```bash
pytest
```
