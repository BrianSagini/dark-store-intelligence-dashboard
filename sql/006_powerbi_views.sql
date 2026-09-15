-- Power BI-facing views for Project 2. Passthrough/join views over tables
-- already populated by 002-005 -- no logic duplicated here.

CREATE OR REPLACE VIEW dark_store.powerbi_sales_summary AS
SELECT
    m.store_id, s.name AS store_name, s.region, s.country,
    m.metric_date, m.revenue, m.orders_count, m.units_sold,
    ROUND(m.revenue / NULLIF(m.orders_count, 0), 2) AS avg_order_value
FROM dark_store.store_daily_metrics m
JOIN dark_store.stores s ON s.store_id = m.store_id;

CREATE OR REPLACE VIEW dark_store.powerbi_inventory_summary AS
SELECT
    i.store_id, s.name AS store_name, i.stock_code, p.description,
    i.avg_daily_demand, i.avg_stock_on_hand, i.days_of_supply,
    i.stockout_days, i.turnover_ratio
FROM dark_store.inventory_analysis i
JOIN dark_store.stores s ON s.store_id = i.store_id
LEFT JOIN dark_store.products p ON p.stock_code = i.stock_code;

CREATE OR REPLACE VIEW dark_store.powerbi_store_performance AS
SELECT
    p.store_id, s.name AS store_name, s.region, s.country, s.sqft,
    p.month, p.revenue, p.cogs_estimate, p.opex_estimate, p.profit_estimate, p.roi_pct
FROM dark_store.store_profitability p
JOIN dark_store.stores s ON s.store_id = p.store_id;
