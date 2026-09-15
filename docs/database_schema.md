# Database Schema

Postgres 16, database `analytics`, schema `dark_store`. Read-only role `analytics_ro` has
`SELECT` on everything here.

| Table | Grain | Notes |
|---|---|---|
| `stores` | 1 row/store (6) | fully synthetic (`is_synthetic`) |
| `products` | 1 row/`stock_code` | real (from UCI dataset) |
| `orders` | 1 row/invoice | real order header; `store_id` assignment synthetic |
| `order_items` | 1 row/invoice/stock_code | real line items |
| `inventory_snapshots` | 1 row/store/product/day | fully synthetic simulation (`is_synthetic`) |
| `store_daily_metrics`, `inventory_analysis`, `store_profitability`, `cross_store_correlation` | SQL-computed analytics | see `docs/methodology.md` |
| `powerbi_sales_summary`, `powerbi_inventory_summary`, `powerbi_store_performance` | views | pure passthrough/join views for Power BI |

Every fact table has a natural-key primary key, so `ON CONFLICT DO UPDATE`/`DO NOTHING` upserts
make reruns idempotent by construction.
