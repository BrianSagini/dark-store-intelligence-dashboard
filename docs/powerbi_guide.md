# Power BI Guide

## Status — read this first

A real `.pbip` project exists at `powerbi/DarkStoreIntelligence.pbip`. Real and complete: 4 tables
(3 fact views + a genuine `Stores` dimension), 3 relationships, all 8 DAX measures below, **23
real visual objects across all 4 pages** (19 data visuals + a header/footer text box per page —
see [Visual inventory](#visual-inventory)), a custom theme (`DarkStoreTheme.json`, wired into
`report.json`), and semantic accent colors (see Design system).

**Power BI Desktop validation status: FULLY VERIFIED. All 4 pages confirmed rendering correctly
with real data, real colors, in Power BI Desktop** (see `docs/evidence/page1_executive_overview.png`
through `page4_store_performance.png`).

The root causes behind the original round-2 bugs (blank charts, no titles, a literal `\$`, wrong
date format, maps disabled for the tenant) were found on the sibling Climate Risk project and
fixed identically here — see Climate's `docs/powerbi_guide.md` for that diagnostic account. This
project's own file was then independently reopened in Desktop and found two *additional* bugs
that the earlier fix round hadn't caught, since they only manifest with the accent colors and
Aggregation-wrapped chart fields added afterward:
1. Every `clusteredColumnChart`/`lineChart` Y-field was a raw unaggregated `Column` reference,
   which renders as a totally empty plot area (no bars, no error). Fixed by pointing each chart at
   its matching existing DAX measure (`Total Revenue`, `Total Stockout Days`, `Avg Turnover Ratio`,
   `Total Profit (Est.)`) or, where none existed (Store Performance's `revenue`), wrapping the
   column in Desktop's own `Aggregation` field shape.
2. `objects.dataPoint.defaultColor` on the two green-accented cards (Total Revenue, Total Profit
   (Est.)) is silently dropped by Desktop on load — cards need `objects.labels[0].properties.color`
   instead. Both fixed and confirmed re-rendering green.

Also fixed here: `themeCollection.baseTheme.reportVersionAtImport` in `report.json` was a bare
string (`"5.55"`) instead of the required `{visual, report, page}` object — this didn't block this
file from opening, but corrupted the identical field and caused a hard "issues that could not be
resolved" load error on the Hiring and Fraud projects (see their guides). Fixed to match Climate's
already-correct shape for consistency, even though this project happened to tolerate it.

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

## Design system — now actually applied, not just documented

Segoe UI. Accents: primary navy `#1B2A4A`, secondary purple `#6C4AB6`, teal `#2E8B99`, positive
green `#2E9E5B`, warning orange `#E67E22`, critical red `#C0392B`.

**Background**: a pale purple-tinted canvas `#F3F0FA` (not neutral gray) behind white visual
containers — same reasoning as Climate's (see that project's guide for the 3 options weighed):
visibly branded without competing with in-chart accent colors. Set via `DarkStoreTheme.json`'s
`visualStyles.*.*.outspace`.

**Per-visual accent colors** (`dataPoint.defaultColor`, single-measure charts only): Revenue by
Store, Revenue Over Time, Revenue by Region, Profit (Est.) by Store, Revenue by Month, and the
Total Revenue/Total Profit cards → positive green (revenue/profit is good). Avg Turnover Ratio by
Store → secondary purple (neutral operational metric). Stockout Days by Store → warning orange (a
problem indicator). Everything else is theme-driven.

**Header/footer**: every page gets a themed header (report — page name + data-source line) and
footer (source + methodology pointer) as real `textbox` visuals.

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
- Store Locations (Sized by Revenue) — Map (bubble) — Category `Stores[name]`, Latitude `Stores[lat]`, Longitude `Stores[lon]`, Size `SalesSummary[Total Revenue]`
- Store Profitability Detail — Table — `StorePerformance[store_name]`, `[month]`, `[revenue]`, `[cogs_estimate]`, `[opex_estimate]`, `[profit_estimate]`, `[roi_pct]`

**Total: 15 visuals across 4 pages.**

## Power BI Service publication: BLOCKED

Needs a Power BI account/workspace and an On-premises Data Gateway for this local Postgres source
— neither exists here.
