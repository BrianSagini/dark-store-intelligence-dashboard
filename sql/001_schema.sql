-- Dark Store Intelligence -- schema.
-- orders/order_items are REAL (UCI Online Retail II, "Year 2010-2011" sheet).
-- stores.is_synthetic and inventory_snapshots.is_synthetic flag the
-- invented dimensions layered on top -- see docs/methodology_dark_store.md.

CREATE TABLE IF NOT EXISTS dark_store.stores (
    store_id       TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    region         TEXT,
    country        TEXT,
    lat            DOUBLE PRECISION,
    lon            DOUBLE PRECISION,
    sqft           INT,
    opening_date   DATE,
    is_synthetic   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dark_store.products (
    stock_code            TEXT PRIMARY KEY,
    description            TEXT,
    reference_unit_price   NUMERIC
);

CREATE TABLE IF NOT EXISTS dark_store.orders (
    invoice_no    TEXT PRIMARY KEY,
    store_id      TEXT NOT NULL REFERENCES dark_store.stores(store_id),
    order_date    TIMESTAMP NOT NULL,
    customer_id   TEXT,
    country       TEXT
);

CREATE TABLE IF NOT EXISTS dark_store.order_items (
    invoice_no    TEXT NOT NULL REFERENCES dark_store.orders(invoice_no),
    stock_code    TEXT NOT NULL REFERENCES dark_store.products(stock_code),
    store_id      TEXT NOT NULL REFERENCES dark_store.stores(store_id),
    quantity      INT NOT NULL,
    unit_price    NUMERIC NOT NULL,
    revenue       NUMERIC NOT NULL,
    order_date    DATE NOT NULL,
    PRIMARY KEY (invoice_no, stock_code)
);

CREATE TABLE IF NOT EXISTS dark_store.inventory_snapshots (
    store_id         TEXT NOT NULL REFERENCES dark_store.stores(store_id),
    stock_code       TEXT NOT NULL REFERENCES dark_store.products(stock_code),
    snapshot_date    DATE NOT NULL,
    units_demanded   INT NOT NULL,
    stock_on_hand    INT NOT NULL,
    restocked        BOOLEAN NOT NULL DEFAULT FALSE,
    is_synthetic     BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (store_id, stock_code, snapshot_date)
);

CREATE TABLE IF NOT EXISTS dark_store.store_daily_metrics (
    store_id       TEXT NOT NULL REFERENCES dark_store.stores(store_id),
    metric_date    DATE NOT NULL,
    revenue        NUMERIC,
    orders_count   INT,
    units_sold     INT,
    PRIMARY KEY (store_id, metric_date)
);

CREATE TABLE IF NOT EXISTS dark_store.inventory_analysis (
    store_id            TEXT NOT NULL REFERENCES dark_store.stores(store_id),
    stock_code          TEXT NOT NULL REFERENCES dark_store.products(stock_code),
    avg_daily_demand    DOUBLE PRECISION,
    avg_stock_on_hand   DOUBLE PRECISION,
    days_of_supply      DOUBLE PRECISION,
    stockout_days       INT,
    turnover_ratio       DOUBLE PRECISION,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, stock_code)
);

CREATE TABLE IF NOT EXISTS dark_store.store_profitability (
    store_id           TEXT NOT NULL REFERENCES dark_store.stores(store_id),
    month              DATE NOT NULL,
    revenue            NUMERIC,
    cogs_estimate      NUMERIC,
    opex_estimate      NUMERIC,
    profit_estimate    NUMERIC,
    roi_pct            DOUBLE PRECISION,
    computed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, month)
);

CREATE TABLE IF NOT EXISTS dark_store.cross_store_correlation (
    store_id_a      TEXT NOT NULL REFERENCES dark_store.stores(store_id),
    store_id_b      TEXT NOT NULL REFERENCES dark_store.stores(store_id),
    weekly_revenue_correlation   DOUBLE PRECISION,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id_a, store_id_b)
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_date ON dark_store.order_items(order_date);
CREATE INDEX IF NOT EXISTS idx_inventory_snapshot_date ON dark_store.inventory_snapshots(snapshot_date);

-- Demand-forecasting model evaluation. Same shape as fraud_pattern's and
-- climate_risk's model_evaluation (model_name, real metrics, computed_at)
-- for consistency across the portfolio's ML tables -- MAE/RMSE here since
-- this is a regression problem, not classification.
CREATE TABLE IF NOT EXISTS dark_store.model_evaluation (
    model_name    TEXT NOT NULL,
    mae           DOUBLE PRECISION NOT NULL,
    rmse          DOUBLE PRECISION NOT NULL,
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (model_name)
);

-- Test-set-only demand predictions (mirrors fraud_pattern.anomaly_scores'
-- and climate_risk.risk_model_predictions' pattern of only ever writing
-- held-out-set predictions, never train-set ones). Both the XGBoost model
-- and the seasonal-naive baseline are written, keyed by model_name.
CREATE TABLE IF NOT EXISTS dark_store.demand_forecast_predictions (
    store_id           TEXT NOT NULL REFERENCES dark_store.stores(store_id),
    stock_code         TEXT NOT NULL REFERENCES dark_store.products(stock_code),
    snapshot_date       DATE NOT NULL,
    model_name          TEXT NOT NULL,
    predicted_demand    DOUBLE PRECISION NOT NULL,
    actual_demand       INT NOT NULL,
    computed_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, stock_code, snapshot_date, model_name)
);

-- The business-value comparison: the existing fixed-restock-to-300 policy
-- vs. a forecast-informed restock policy, replayed over the same held-out
-- real demand for each dense (store, product) pair. See docs/model_card.md.
CREATE TABLE IF NOT EXISTS dark_store.reorder_policy_comparison (
    store_id            TEXT NOT NULL REFERENCES dark_store.stores(store_id),
    stock_code          TEXT NOT NULL REFERENCES dark_store.products(stock_code),
    policy_name          TEXT NOT NULL,
    stockout_days        INT NOT NULL,
    avg_stock_on_hand    DOUBLE PRECISION NOT NULL,
    computed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (store_id, stock_code, policy_name)
);

-- H2O AutoML leaderboard from demand_forecast_model.ipynb's "AutoML sanity
-- check (H2O)" section -- the aml.leaderboard object itself doesn't survive
-- that notebook's session, so this is the persisted record of it, read by
-- the small automl/app.py Streamlit page (separate from the main
-- dashboard). One row per model H2O trained in that AutoML run, ranked by
-- its own sort_metric (MAE here).
CREATE TABLE IF NOT EXISTS dark_store.automl_leaderboard (
    model_id                TEXT PRIMARY KEY,
    algorithm                TEXT NOT NULL,
    rank                     INT NOT NULL,
    is_leader                BOOLEAN NOT NULL DEFAULT FALSE,
    auc                      DOUBLE PRECISION,
    logloss                  DOUBLE PRECISION,
    aucpr                    DOUBLE PRECISION,
    mean_per_class_error     DOUBLE PRECISION,
    mae                      DOUBLE PRECISION,
    rmse                     DOUBLE PRECISION,
    mse                      DOUBLE PRECISION,
    rmsle                    DOUBLE PRECISION,
    mean_residual_deviance   DOUBLE PRECISION,
    target_column            TEXT NOT NULL,
    project_name             TEXT NOT NULL,
    trained_at               TIMESTAMPTZ NOT NULL
);
