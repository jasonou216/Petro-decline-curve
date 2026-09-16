# Power BI measures

DAX measures for the companion report, built against `fact_cycle` (imported from `bi_exports/`). Written here first so the report itself stays reviewable in a diff, Power BI Desktop's own file format isn't.

Relationships (Model view): `dim_battery[Battery]` → `fact_cycle[Battery]` (1:many), `dim_well[WellID]` → `fact_cycle[WellID]` (1:many), both single-direction filtering, fact table on the many side. Classic star, `fact_cycle` doesn't need to go through `dim_well` to reach `dim_battery`.

## Total EUR

```
Total EUR = SUM(fact_cycle[EUR])
```

## Total NPV

```
Total NPV = SUM(fact_cycle[NPV])
```

Both are blank for low-confidence cycles in the source data (`fact_cycle[IsHighConfidence] = FALSE`), so these sums already only cover high-confidence cycles without an extra filter, matching how the Streamlit dashboard scopes its own totals.

## % Negative NPV cycles

```
% Negative NPV Cycles =
VAR NegativeCycles = CALCULATE(COUNTROWS(fact_cycle), fact_cycle[NPV] < 0)
VAR PricedCycles = CALCULATE(COUNTROWS(fact_cycle), NOT ISBLANK(fact_cycle[NPV]))
RETURN
    DIVIDE(NegativeCycles, PricedCycles)
```

`DIVIDE` instead of `/` to avoid a divide-by-zero error if a filter context ever produces zero priced cycles. Denominator is priced cycles, not all cycles, low-confidence ones were never priced at all, not priced-and-zero.

## Median cycle NPV

```
Median Cycle NPV = MEDIANX(fact_cycle, fact_cycle[NPV])
```

`MEDIANX` iterates row by row rather than assuming a pre-aggregated value, correct for a raw fact table like this one.

## Cycle-over-cycle NPV change

Two versions, same idea, different DAX construct depending on where you need it.

**Calculated column** (put this directly on `fact_cycle`, needed if you want every row's change visible in a table/matrix). `EARLIER` only works inside a calculated column, not a measure, it refers back to the outer row context from inside the `FILTER`:

```
Prior Cycle NPV =
CALCULATE(
    SUM(fact_cycle[NPV]),
    FILTER(
        fact_cycle,
        fact_cycle[WellID] = EARLIER(fact_cycle[WellID])
            && fact_cycle[CycleNumber] = EARLIER(fact_cycle[CycleNumber]) - 1
    )
)

NPV Change vs Prior Cycle = fact_cycle[NPV] - fact_cycle[Prior Cycle NPV]
```

**Measure, variable-based** (use this for a card or a visual that reacts to whatever well/cycle is currently selected or filtered, e.g. a drillthrough page):

```
Cycle NPV Change (Measure) =
VAR CurrentWell = SELECTEDVALUE(fact_cycle[WellID])
VAR CurrentCycle = SELECTEDVALUE(fact_cycle[CycleNumber])
VAR CurrentNPV = SUM(fact_cycle[NPV])
VAR PriorNPV =
    CALCULATE(
        SUM(fact_cycle[NPV]),
        fact_cycle[WellID] = CurrentWell,
        fact_cycle[CycleNumber] = CurrentCycle - 1
    )
RETURN
    CurrentNPV - PriorNPV
```

`SELECTEDVALUE` returns blank if more than one well/cycle is in context (e.g. a table with no row-level filter applied), which is correct, "prior cycle" isn't a meaningful number aggregated across many wells at once.
