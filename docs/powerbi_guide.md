# Power BI Guide

## Status — read this first

A real `.pbip` project exists at `powerbi/DarkStoreIntelligence.pbip`, generated programmatically
— **never opened in Power BI Desktop, so not validated.** Real and complete: 4 tables (3 fact
views + a genuine `Stores` dimension from `dark_store.stores`), 3 relationships, all 8 DAX
measures below. Placeholder: 4 report pages exist, named correctly, zero visuals.

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

## Pages

1. **Executive Overview** — cards: Total Revenue, Total Orders, Avg Order Value, Total Profit
   (Est.); revenue-by-store bar (green where ROI positive, red where negative). Label real
   (revenue/orders) vs. estimated (profit/ROI) explicitly.
2. **Sales Performance** — revenue trend over `metric_date`; revenue by store/region; date/store
   slicers.
3. **Product & Inventory Intelligence** — turnover ratio and days-of-supply by product (top/bottom
   10 = fast/slow movers); stockout days by store. Note: inventory is a simulation, not measured
   stock.
4. **Store Performance** — profit/ROI by store and month, with the real-vs-estimated disclosure
   repeated.

## Power BI Service publication: BLOCKED

Needs a Power BI account/workspace and an On-premises Data Gateway for this local Postgres source
— neither exists here.
