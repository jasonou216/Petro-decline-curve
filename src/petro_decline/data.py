"""Pull and clean Alberta well production data from Petrinex.

Petrinex publishes one province-wide "Conventional Volumetric Data" file per month
at ``PETRINEX_URL_TEMPLATE``. Each file is a full AB dump (~500k rows, ~120MB
uncompressed) double-zipped by the API (an outer .zip containing an inner .zip
containing the actual .CSV) — we only need a few thousand rows out of it (our two
target batteries), so `load_and_filter_month` unzips and filters entirely in memory
and never writes the province-wide file to disk at all. Only the small,
already-filtered per-month result is written, to `data/processed/monthly/` — that
also serves as the resume checkpoint for `pull_range`.

Records must be filtered to `ActivityID == 'PROD'` (excludes SHUTIN/INVCL/INVOP/
REC/DISP/FLARE/FUEL/DIFF — those are status, accounting, or facility-transfer
records, not wellbore production) and `FromToIDType == 'WI'` (individual wellbore
records, as opposed to facility-to-facility transfers). Cold Lake is a CSS thermal
asset, so injector wells appear in the well-level data alongside producers and must
be identified and excluded before aggregating (see `identify_injectors`) — a CSS
pad's producing total would be corrupted by injector volumes.
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

PETRINEX_URL_TEMPLATE = "https://www.petrinex.gov.ab.ca/publicdata/API/Files/AB/Vol/{year_month}/CSV"

PROCESSED_DIR = Path("data/processed")
MONTHLY_DIR = PROCESSED_DIR / "monthly"  # per-month filtered well-level checkpoints (enables resume)

# ReportingFacilityID -> human-readable name, confirmed against the June 2026 file.
TARGET_BATTERIES = {
    "ABBT0051212": "Mahihkan Battery 02-21",
    "ABBT0119087": "Nabiye 11-23",
}

PROD_ACTIVITY_ID = "PROD"
WELL_FROM_TO_TYPE = "WI"

# Some operators report bitumen under ProductID 'OIL', others under 'BIT'.
OIL_LIKE_PRODUCTS = {"OIL", "BIT"}
INJECTOR_VOLUME_THRESHOLD = 1e-6  # m3, summed across all pulled history


def month_range(start: str, end: str) -> list[str]:
    """List 'YYYY-MM' strings from `start` to `end`, inclusive.

    Args:
        start: first month, as 'YYYY-MM'.
        end: last month, as 'YYYY-MM'.

    Returns:
        Ascending list of 'YYYY-MM' strings.
    """
    start_year, start_month = (int(part) for part in start.split("-"))
    end_year, end_month = (int(part) for part in end.split("-"))

    months = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def monthly_checkpoint_path(year_month: str) -> Path:
    """Path to the small, filtered well-level CSV that checkpoints one month's pull."""
    return MONTHLY_DIR / f"{year_month}_filtered.csv"


def fetch_month_zip(year_month: str, timeout: int = 180) -> bytes | None:
    """Download one month's province-wide Petrinex Vol file (still double-zipped).

    Args:
        year_month: month to fetch, as 'YYYY-MM'.
        timeout: request timeout in seconds.

    Returns:
        Raw response bytes, or None if the month isn't available (network error or
        non-200 response) — logged and skipped rather than raising, so a multi-year
        pull doesn't die on one missing/unpublished month.
    """
    url = PETRINEX_URL_TEMPLATE.format(year_month=year_month)
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning("%s: request failed (%s) — skipping", year_month, exc)
        return None
    if response.status_code != 200:
        logger.warning(
            "%s: HTTP %s — skipping (file may not be published yet)", year_month, response.status_code
        )
        return None
    return response.content


def extract_csv_bytes(outer_zip_bytes: bytes) -> bytes:
    """Unwrap the API's outer-zip-containing-inner-zip-containing-CSV, in memory.

    Args:
        outer_zip_bytes: raw bytes as returned by the Petrinex Files API.

    Returns:
        The raw CSV file bytes.
    """
    with zipfile.ZipFile(io.BytesIO(outer_zip_bytes)) as outer_zip:
        inner_zip_bytes = outer_zip.read(outer_zip.namelist()[0])
    with zipfile.ZipFile(io.BytesIO(inner_zip_bytes)) as inner_zip:
        return inner_zip.read(inner_zip.namelist()[0])


def load_and_filter_month(year_month: str) -> tuple[pd.DataFrame, int] | None:
    """Download, unzip, and filter one month to well-level PROD rows for our batteries.

    Downloads straight into memory and filters before anything touches disk — a
    province-wide month is ~120MB uncompressed for ~500k rows, and we only keep a
    few thousand of them, so there's no reason to ever write the full file to
    `data/raw/`.

    Args:
        year_month: month to pull, as 'YYYY-MM'.

    Returns:
        (filtered well-level rows, compressed download size in bytes), or None if
        the month wasn't available.
    """
    outer_zip_bytes = fetch_month_zip(year_month)
    if outer_zip_bytes is None:
        return None

    csv_bytes = extract_csv_bytes(outer_zip_bytes)
    print(
        f"{year_month}: downloaded {len(outer_zip_bytes) / 1e6:.1f} MB compressed "
        f"-> {len(csv_bytes) / 1e6:.1f} MB CSV"
    )

    df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str)
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")

    filtered = df[
        df["ReportingFacilityID"].isin(TARGET_BATTERIES)
        & (df["ActivityID"] == PROD_ACTIVITY_ID)
        & (df["FromToIDType"] == WELL_FROM_TO_TYPE)
    ].copy()

    filtered = filtered[["ProductionMonth", "ReportingFacilityID", "FromToID", "ProductID", "Volume"]]
    return filtered, len(outer_zip_bytes)


def identify_injectors(well_level: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split well-level production into (producers, injectors).

    A well is classified as an injector if its OIL/BIT volume summed across the
    *entire pulled history* is at or below `INJECTOR_VOLUME_THRESHOLD` — steam
    injectors report zero/near-zero oil or bitumen production even though they may
    report other activity. Injectors are returned separately rather than silently
    dropped, so they can be reviewed.

    Args:
        well_level: well-level production rows (all months, all target batteries),
            as returned by `load_and_filter_month`.

    Returns:
        (producers, injectors) — both well-level DataFrames, same columns as the
        input, partitioned by well.
    """
    # reindex against every well present in well_level: a well with no OIL/BIT rows
    # at all (never appears in oil_like) must still count as zero oil, not be
    # silently excluded from consideration.
    all_wells = well_level.set_index(["ReportingFacilityID", "FromToID"]).index.unique()
    oil_like = well_level[well_level["ProductID"].isin(OIL_LIKE_PRODUCTS)]
    oil_totals = oil_like.groupby(["ReportingFacilityID", "FromToID"])["Volume"].sum()
    oil_totals = oil_totals.reindex(all_wells, fill_value=0.0)
    injector_wells = oil_totals[oil_totals <= INJECTOR_VOLUME_THRESHOLD].index

    is_injector = well_level.set_index(["ReportingFacilityID", "FromToID"]).index.isin(injector_wells)
    injectors = well_level[is_injector]
    producers = well_level[~is_injector]
    return producers, injectors


def well_oil_series(well_level: pd.DataFrame, well_id: str) -> pd.Series:
    """Monthly OIL volume for one well, indexed by ProductionMonth.

    Reindexed to a complete monthly range between the well's first and last
    reported month, with missing months filled as 0 — a month absent from
    Petrinex for this well means it wasn't producing (soak phase, shut-in),
    the same "absent means zero" treatment `identify_injectors` uses.

    Promoted here from notebooks/explore_cycle_detection.py once cycle
    detection was validated — this is the one place that shapes well-level
    rows into the per-well monthly series both cycle detection and Arps
    fitting (decline.py) build on.
    """
    well_df = well_level[(well_level["FromToID"] == well_id) & (well_level["ProductID"] == "OIL")]
    series = well_df.set_index("ProductionMonth")["Volume"].sort_index()
    full_range = pd.date_range(series.index.min(), series.index.max(), freq="MS")
    return series.reindex(full_range, fill_value=0.0)


def aggregate_pad_production(well_level: pd.DataFrame) -> pd.DataFrame:
    """Sum monthly PROD volumes across producing wells, per battery per product.

    Args:
        well_level: well-level production rows for *producing* wells only (run
            `identify_injectors` first and pass in the producers half).

    Returns:
        One row per (ReportingFacilityID, ProductionMonth, ProductID) with summed
        Volume — the pad-level time series `decline.fit_decline` fits curves to.
        Batteries are kept separate (not combined) so they can be compared.
    """
    return (
        well_level.groupby(["ReportingFacilityID", "ProductionMonth", "ProductID"], as_index=False)["Volume"]
        .sum()
        .sort_values(["ReportingFacilityID", "ProductID", "ProductionMonth"])
        .reset_index(drop=True)
    )


def pull_range(start: str, end: str) -> pd.DataFrame:
    """Pull, filter, and checkpoint every month in [start, end], resuming if interrupted.

    For each month: skip it if its checkpoint CSV already exists in
    `MONTHLY_DIR` (resume support), otherwise download+filter it via
    `load_and_filter_month` and write the checkpoint. Prints running totals
    (files processed, cumulative download size, cumulative filtered row count)
    after every month so progress is visible and a bad pull can be caught early.

    Args:
        start: first month, as 'YYYY-MM'.
        end: last month, as 'YYYY-MM'.

    Returns:
        Well-level production for every successfully pulled month, concatenated.
    """
    MONTHLY_DIR.mkdir(parents=True, exist_ok=True)

    months = month_range(start, end)
    total_download_mb = 0.0
    total_rows = 0
    monthly_frames = []

    for i, year_month in enumerate(months, start=1):
        checkpoint = monthly_checkpoint_path(year_month)

        if checkpoint.exists():
            month_df = pd.read_csv(checkpoint, dtype={"ReportingFacilityID": str, "FromToID": str, "ProductID": str})
            print(f"{year_month}: using existing checkpoint ({len(month_df)} rows)")
        else:
            result = load_and_filter_month(year_month)
            if result is None:
                continue
            month_df, download_bytes = result
            total_download_mb += download_bytes / 1e6
            month_df.to_csv(checkpoint, index=False)

        total_rows += len(month_df)
        monthly_frames.append(month_df)

        print(
            f"[{i}/{len(months)}] {year_month} done - "
            f"cumulative download {total_download_mb:.1f} MB, cumulative rows {total_rows}"
        )

    if not monthly_frames:
        return pd.DataFrame(columns=["ProductionMonth", "ReportingFacilityID", "FromToID", "ProductID", "Volume"])
    return pd.concat(monthly_frames, ignore_index=True)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Pull Cold Lake battery production from Petrinex.")
    parser.add_argument("--start", default="2022-01")  # earliest month the public Files API serves; see CLAUDE.md
    parser.add_argument("--end", default=date.today().strftime("%Y-%m"))
    args = parser.parse_args()

    well_level_all = pull_range(args.start, args.end)
    producers, injectors = identify_injectors(well_level_all)

    # Tag every well (producer or injector) on the full well-level output, rather than
    # dropping injectors from it, so individual well behavior can be spot-checked either way.
    injector_keys = injectors[["ReportingFacilityID", "FromToID"]].drop_duplicates()
    injector_keys["IsInjector"] = True
    well_level_all = well_level_all.merge(injector_keys, on=["ReportingFacilityID", "FromToID"], how="left")
    well_level_all["IsInjector"] = well_level_all["IsInjector"].fillna(False).astype(bool)

    if injector_keys.empty:
        print("No injector wells flagged in this pull.")
    else:
        injector_keys.to_csv(PROCESSED_DIR / "injector_wells.csv", index=False)
        print(f"Flagged {len(injector_keys)} injector well(s) -> data/processed/injector_wells.csv")

    for facility_id, name in TARGET_BATTERIES.items():
        battery_wells = well_level_all[well_level_all["ReportingFacilityID"] == facility_id]
        if battery_wells.empty:
            print(f"{name} ({facility_id}): no rows pulled - skipping output")
            continue

        battery_producers = battery_wells[~battery_wells["IsInjector"]]
        pad_level = aggregate_pad_production(battery_producers)

        safe_name = name.lower().replace(" ", "_")
        battery_wells.to_csv(PROCESSED_DIR / f"{safe_name}_well_level.csv", index=False)
        pad_level.to_csv(PROCESSED_DIR / f"{safe_name}_pad_level.csv", index=False)
        print(
            f"{name} ({facility_id}): {len(battery_wells)} well-level rows "
            f"({(battery_wells['IsInjector']).sum()} injector rows), {len(pad_level)} pad-level rows"
        )
