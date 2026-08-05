# Petro Decline Curves

Portfolio project analyzing Alberta well production data to build a decline-curve
type curve and economics model, presented as a Streamlit dashboard.

Built as part of internship applications for upstream oil & gas roles.

## What it does

1. Pulls monthly production data from [Petrinex](https://www.petrinex.gov.ab.ca/) for
   two Cold Lake CSS batteries — Mahihkan 02-21 (`ABBT0051212`) and Nabiye 11-23
   (`ABBT0119087`) — and aggregates producing-well volumes to the pad/battery level
   (Cold Lake is CSS thermal, so individual wells cycle steam/soak/produce and don't
   follow a standard well-level Arps decline; see `src/petro_decline/data.py`).
2. Fits Arps decline curve models (exponential, hyperbolic, harmonic) to each
   battery's pad-level production history.
3. Calculates Estimated Ultimate Recovery (EUR) from the fitted curves.
4. Compares Mahihkan and Nabiye as a type-curve pair for the **Cold Lake** play.
5. Applies a basic economics layer (NPV, IRR) to the forecast.
6. Presents the results in an interactive Streamlit dashboard.

## Project structure

```
petro-decline-curves/
├── app.py                    # Streamlit dashboard entry point
├── src/petro_decline/
│   ├── data.py                # Petrinex data pull + cleaning
│   ├── decline.py             # Arps decline curve models + fitting
│   ├── eur.py                 # EUR calculation
│   └── economics.py           # NPV / IRR
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

## Running

```bash
streamlit run app.py
```

## Testing

```bash
pytest
```
