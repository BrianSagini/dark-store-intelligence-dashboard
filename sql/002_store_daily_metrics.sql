-- Daily revenue/orders/units per store, from real order_items.
INSERT INTO dark_store.store_daily_metrics (store_id, metric_date, revenue, orders_count, units_sold)
SELECT
    store_id,
    order_date AS metric_date,
    SUM(revenue) AS revenue,
    COUNT(DISTINCT invoice_no) AS orders_count,
    SUM(quantity) AS units_sold
FROM dark_store.order_items
GROUP BY store_id, order_date
ON CONFLICT (store_id, metric_date) DO UPDATE SET
    revenue = EXCLUDED.revenue,
    orders_count = EXCLUDED.orders_count,
    units_sold = EXCLUDED.units_sold;
