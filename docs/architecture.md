# Architecture

```mermaid
flowchart TB
    Petrinex(("Petrinex<br/>public API"))
    EIA(("EIA<br/>public API"))

    subgraph Pipeline["Offline pipeline (notebooks/ + src/petro_decline)"]
        DataPy["data.py"]
        CycleDetect["cycle detection"]
        DeclinePy["decline.py"]
        EurPy["eur.py"]
        EconomicsPy["economics.py"]
    end

    Processed[("data/processed/<br/>*_well_level.csv")]
    CyclesFull[("cycles_full.csv")]
    FitsFull[("decline_fits_full.csv")]
    EconFull[("decline_economics_full.csv")]

    Petrinex -->|production data| DataPy
    DataPy -->|"filtered in memory,<br/>raw file never written to disk"| Processed
    Processed -->|monthly series| CycleDetect
    CycleDetect --> CyclesFull
    CyclesFull -->|fittable cycles| DeclinePy
    DeclinePy --> FitsFull
    FitsFull -->|high-confidence subset| EurPy
    EurPy -->|EUR| EconomicsPy
    EIA -.->|live price,<br/>config.yaml fallback| EconomicsPy
    EconomicsPy --> EconFull

    App["app.py<br/>(Streamlit dashboard)"]
    BiExport["bi_export.py"]
    BiCsvs[("bi_exports/*.csv")]
    Pbix["Power BI report<br/>(.pbix)"]

    Processed --> App
    CyclesFull --> App
    FitsFull --> App
    EconFull --> App
    EIA -.->|live price,<br/>what-if panel| App

    CyclesFull --> BiExport
    FitsFull --> BiExport
    EconFull --> BiExport
    BiExport --> BiCsvs
    BiCsvs -->|manual import| Pbix
```

`app.py` reads the committed CSVs for its headline numbers, but also calls `decline.py` and `economics.py` directly at runtime (redrawing fitted curves, live what-if repricing), it isn't purely a static-file reader. `bi_export.py` only ever reads already-computed CSVs, it has no API or pricing dependency of its own.
