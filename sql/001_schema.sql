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
