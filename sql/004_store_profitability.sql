-- Monthly store profitability.
--
-- revenue is real (from store_daily_metrics). cogs_estimate and
-- opex_estimate are synthetic assumptions (documented in
-- docs/methodology_dark_store.md): COGS = 42% of revenue (illustrative
-- margin assumption), opex = $4/sqft/month (illustrative rent+labor
-- proxy). roi_pct = profit / opex, i.e. return on monthly operating spend.

INSERT INTO dark_store.store_profitability (store_id, month, revenue, cogs_estimate, opex_estimate, profit_estimate, roi_pct, computed_at)
SELECT
    m.store_id,
    date_trunc('month', m.metric_date)::date AS month,
    SUM(m.revenue) AS revenue,
    ROUND(SUM(m.revenue) * 0.42, 2) AS cogs_estimate,
    ROUND(s.sqft * 4.0, 2) AS opex_estimate,
    ROUND(SUM(m.revenue) - (SUM(m.revenue) * 0.42) - (s.sqft * 4.0), 2) AS profit_estimate,
    CASE WHEN s.sqft > 0 THEN
        ROUND((((SUM(m.revenue) - (SUM(m.revenue) * 0.42) - (s.sqft * 4.0)) / (s.sqft * 4.0)) * 100)::numeric, 2)
    ELSE NULL END AS roi_pct,
    now()
FROM dark_store.store_daily_metrics m
JOIN dark_store.stores s ON s.store_id = m.store_id
GROUP BY m.store_id, date_trunc('month', m.metric_date), s.sqft
ON CONFLICT (store_id, month) DO UPDATE SET
    revenue = EXCLUDED.revenue,
    cogs_estimate = EXCLUDED.cogs_estimate,
    opex_estimate = EXCLUDED.opex_estimate,
    profit_estimate = EXCLUDED.profit_estimate,
    roi_pct = EXCLUDED.roi_pct,
    computed_at = EXCLUDED.computed_at;
