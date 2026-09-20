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
| `model_evaluation` | 1 row/model | real MAE/RMSE for `xgboost_demand_model` and `seasonal_naive_dow` — see `docs/model_card.md` |
| `demand_forecast_predictions` | 1 row/store/product/test-day/model | held-out daily forecasts only (never train-set rows), both models |
| `reorder_policy_comparison` | 1 row/store/product/policy | `fixed_restock_300` vs. `forecast_plus_safety_buffer`, replayed over the same held-out real demand |
| `powerbi_sales_summary`, `powerbi_inventory_summary`, `powerbi_store_performance` | views | pure passthrough/join views for Power BI |

Every fact table has a natural-key primary key, so `ON CONFLICT DO UPDATE`/`DO NOTHING` upserts
make reruns idempotent by construction.
