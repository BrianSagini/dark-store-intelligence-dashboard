# Power BI Guide

## Status — read this first

A real `.pbip` project exists at `powerbi/DarkStoreIntelligence.pbip`. Real and complete: 4 tables
(3 fact views + a genuine `Stores` dimension from `dark_store.stores`), 3 relationships, all 8 DAX
measures below, and **14 real visual objects across all 4 pages** (see
[Visual inventory](#visual-inventory)) — every one binds to an actual table/column/measure.

**Power BI Desktop validation status: NOT VERIFIED.** This `.pbip`'s sibling project (Climate
Risk) was confirmed *openable* by Power BI Desktop in one clean, safe test — full authoring ribbon,
"Loading report" state. A second validation attempt on that same file captured unrelated content
from another window on this live desktop instead (a focus-tracking failure, not a Power BI issue)
— deleted immediately, never committed — and after that second incident, further screenshot-based
validation was stopped entirely by explicit decision, before reaching this repo specifically. The
outer project structure follows the same pattern already confirmed acceptable; **the visual JSON
below was authored to the best available knowledge of the PBIR schema but was never itself opened
in Power BI Desktop.** If you open this file and something doesn't render, that's real information.

## Data connectivity

Get Data → Database → PostgreSQL database → `localhost:5433` / `analytics` / `analytics_ro`
(password from your `.env`). Mode: **Import**.

## Tables, relationships, measures

Tables: `dark_store.stores` (dimension), `dark_store.powerbi_sales_summary`,
`powerbi_inventory_summary`, `powerbi_store_performance` (facts, all keyed on `store_id`).

Relationships: `Stores[store_id]` (1) → each fact table's `store_id` (*).

```dax
Total Revenue = SUM(powerbi_sales_summary[revenue])
Total Orders = SUM(powerbi_sales_summary[orders_count])
Avg Order Value = DIVIDE([Total Revenue], [Total Orders])
Total Profit (Est.) = SUM(powerbi_store_performance[profit_estimate])
Avg ROI % = AVERAGE(powerbi_store_performance[roi_pct])
Avg Turnover Ratio = AVERAGE(powerbi_inventory_summary[turnover_ratio])
Total Stockout Days = SUM(powerbi_inventory_summary[stockout_days])
Avg Days of Supply = AVERAGE(powerbi_inventory_summary[days_of_supply])
```

## Design system

Base: near-white `#F7F8FA` background, Segoe UI. This project's accents: primary navy `#1B2A4A`,
secondary purple `#6C4AB6`, teal `#2E8B99`, positive green `#2E9E5B` (revenue/profit up), warning
orange `#E67E22` (stock concern), critical red `#C0392B` (loss/stockout).

## Visual inventory

Every visual below is a real object in `powerbi/DarkStoreIntelligence.Report/definition/pages/*/visuals/`.

**Page 1 — Executive Overview**
- Total Revenue — Card — `SalesSummary[Total Revenue]`
- Total Orders — Card — `SalesSummary[Total Orders]`
- Avg Order Value — Card — `SalesSummary[Avg Order Value]`
- Total Profit (Est.) — Card — `StorePerformance[Total Profit (Est.)]`
- Revenue by Store — Clustered column chart — Category `SalesSummary[store_name]`, Y `SalesSummary[revenue]`
- Store — Slicer — `Stores[name]`

**Page 2 — Sales Performance**
- Revenue Over Time — Line chart — Category `SalesSummary[metric_date]`, Y `SalesSummary[revenue]`
- Revenue by Region — Clustered column chart — Category `SalesSummary[region]`, Y `SalesSummary[revenue]`

**Page 3 — Product & Inventory Intelligence**
- Avg Turnover Ratio by Store — Clustered column chart — Category `InventorySummary[store_name]`, Y `InventorySummary[turnover_ratio]`
- Stockout Days by Store — Clustered column chart — Category `InventorySummary[store_name]`, Y `InventorySummary[stockout_days]`
- Inventory Detail — Table — `InventorySummary[store_name]`, `[stock_code]`, `[description]`, `[days_of_supply]`, `[turnover_ratio]`

**Page 4 — Store Performance**
- Profit (Est.) by Store — Clustered column chart — Category `StorePerformance[store_name]`, Y `StorePerformance[profit_estimate]`
- Revenue by Month — Line chart — Category `StorePerformance[month]`, Y `StorePerformance[revenue]`
- Store Profitability Detail — Table — `StorePerformance[store_name]`, `[month]`, `[revenue]`, `[cogs_estimate]`, `[opex_estimate]`, `[profit_estimate]`, `[roi_pct]`

**Total: 14 visuals across 4 pages.**

## Power BI Service publication: BLOCKED

Needs a Power BI account/workspace and an On-premises Data Gateway for this local Postgres source
— neither exists here.
