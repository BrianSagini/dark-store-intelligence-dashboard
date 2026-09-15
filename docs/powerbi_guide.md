# Power BI Guide

## Status — read this first

A real `.pbip` project exists at `powerbi/DarkStoreIntelligence.pbip`. Real and complete: 4 tables
(3 fact views + a genuine `Stores` dimension), 3 relationships, all 8 DAX measures below, **23
real visual objects across all 4 pages** (19 data visuals + a header/footer text box per page —
see [Visual inventory](#visual-inventory)), a custom theme (`DarkStoreTheme.json`, wired into
`report.json`), and semantic accent colors (see Design system).

**Power BI Desktop validation status: PARTIALLY VERIFIED, via the sibling Climate Risk project.**
The project owner actually opened `ClimateRisk.pbip` and reported real bugs (blank charts, no
titles, a literal `\$`, wrong date format, maps disabled for their tenant) — the root causes were
found and fixed identically across all 4 projects, this one included (see Climate's
`docs/powerbi_guide.md` for the full diagnostic account, not repeated here). **This project's own
file has not been independently reopened** — its fixes and this round's styling (theme,
header/footer, accent colors) are structurally validated (every field/measure reference checked
against the live model, no overlaps, no blank pages) but not yet confirmed by an actual render.

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
