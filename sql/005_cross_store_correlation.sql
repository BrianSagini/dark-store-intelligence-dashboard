-- Cross-store weekly revenue correlation -- a CANNIBALIZATION PROXY, not a
-- true cannibalization measurement. This dataset's store assignment is a
-- deterministic, non-overlapping function of customer country (see
-- pipeline.py's _assign_store), so no two stores ever compete for the same
-- customer's order -- there is no real overlapping catchment area to test
-- for cannibalization. What this view actually shows is how correlated two
-- stores' overall demand trends are (e.g., both riding the same seasonal
-- retail cycle), which is a weaker, different signal. Documented as a
-- limitation in docs/methodology_dark_store.md; do not read high
-- correlation here as evidence of demand shifting between stores.

WITH weekly AS (
    SELECT store_id, date_trunc('week', metric_date)::date AS week, SUM(revenue) AS revenue
    FROM dark_store.store_daily_metrics
    GROUP BY store_id, date_trunc('week', metric_date)
)
INSERT INTO dark_store.cross_store_correlation (store_id_a, store_id_b, weekly_revenue_correlation, computed_at)
SELECT
    a.store_id AS store_id_a,
    b.store_id AS store_id_b,
    corr(a.revenue, b.revenue) AS weekly_revenue_correlation,
    now()
FROM weekly a
JOIN weekly b ON a.week = b.week AND a.store_id < b.store_id
GROUP BY a.store_id, b.store_id
ON CONFLICT (store_id_a, store_id_b) DO UPDATE SET
    weekly_revenue_correlation = EXCLUDED.weekly_revenue_correlation,
    computed_at = EXCLUDED.computed_at;
