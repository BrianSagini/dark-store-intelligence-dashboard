-- Inventory health per (store, product), from the synthetic daily
-- inventory simulation (dark_store.inventory_snapshots).
--
-- Note: the simulation restocks to par the *same day* stock would hit
-- zero (no lead-time lag), so stored stock_on_hand is never <= 0 --
-- `restocked = true` days are used as the stockout-event proxy instead
-- (a day the store would have gone out of stock without an immediate
-- restock). turnover_ratio = annualized demand / avg on-hand stock
-- (unit cost cancels out of the COGS/avg-inventory-value ratio).

INSERT INTO dark_store.inventory_analysis
    (store_id, stock_code, avg_daily_demand, avg_stock_on_hand, days_of_supply, stockout_days, turnover_ratio, computed_at)
SELECT
    store_id,
    stock_code,
    AVG(units_demanded) AS avg_daily_demand,
    AVG(stock_on_hand) AS avg_stock_on_hand,
    CASE WHEN AVG(units_demanded) > 0 THEN AVG(stock_on_hand) / AVG(units_demanded) ELSE NULL END AS days_of_supply,
    COUNT(*) FILTER (WHERE restocked) AS stockout_days,
    CASE WHEN AVG(stock_on_hand) > 0 THEN (AVG(units_demanded) * 365.0) / AVG(stock_on_hand) ELSE NULL END AS turnover_ratio,
    now()
FROM dark_store.inventory_snapshots
GROUP BY store_id, stock_code
ON CONFLICT (store_id, stock_code) DO UPDATE SET
    avg_daily_demand = EXCLUDED.avg_daily_demand,
    avg_stock_on_hand = EXCLUDED.avg_stock_on_hand,
    days_of_supply = EXCLUDED.days_of_supply,
    stockout_days = EXCLUDED.stockout_days,
    turnover_ratio = EXCLUDED.turnover_ratio,
    computed_at = EXCLUDED.computed_at;
