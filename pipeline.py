"""Dark Store Intelligence -- ingestion + transform logic.

Data source: UCI "Online Retail II" dataset
(https://archive.ics.uci.edu/dataset/502/online+retail+ii), CC BY 4.0,
keyless direct download. Verified live on 2026-09-12 (HTTP 200). We use
only the "Year 2010-2011" sheet (~541k real transaction line items,
UK-based online retailer, Dec 2010-Dec 2011) to keep ingestion time
reasonable.

This is REAL transaction data, but it has no store/location, inventory,
or cost dimension at all -- it's a single online retailer's order log.
To make it analyzable as a multi-location "dark store" fulfillment
network, this pipeline layers on a SYNTHETIC dimension:

  - each order is deterministically assigned to one of 6 fulfillment
    "dark stores" based on the customer's country (real field) -- this
    simulates which warehouse would have shipped that real order
  - store metadata (address, sqft, opening date) is synthetic
  - inventory levels are synthetic, simulated day-by-day from each
    store's real observed demand for its top products
  - unit cost / opex assumptions used for profitability are synthetic

All synthetic fields/tables are flagged `is_synthetic = true` and
documented in docs/methodology_dark_store.md.
"""
from __future__ import annotations

import hashlib
import io
import os
import zipfile
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

from shared.database import bulk_upsert_dataframe, get_engine, upsert_dataframe
from shared.validation import validate_dataframe

DATASET_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
SHEET_NAME = "Year 2010-2011"
RAW_DIR = os.path.join(os.path.dirname(__file__), "data_raw")
RAW_XLSX_PATH = os.path.join(RAW_DIR, "online_retail_II.xlsx")
EVIDENCE_DIR = os.path.join(os.path.dirname(__file__), "docs", "evidence")
TOP_N_PRODUCTS_FOR_INVENTORY = 150
SYNTHETIC_STARTING_STOCK = 300
SYNTHETIC_RESTOCK_PAR_LEVEL = 300
SYNTHETIC_COGS_RATE = 0.42  # illustrative: cost of goods as a fraction of unit price
RNG_SEED = 7

STORES = [
    {"store_id": "LON", "name": "London Dark Store", "region": "Greater London", "country": "United Kingdom", "lat": 51.5072, "lon": -0.1276, "sqft": 8000, "opening_date": "2020-01-15"},
    {"store_id": "MAN", "name": "Manchester Dark Store", "region": "North West England", "country": "United Kingdom", "lat": 53.4808, "lon": -2.2426, "sqft": 6500, "opening_date": "2020-03-01"},
    {"store_id": "EDI", "name": "Edinburgh Dark Store", "region": "Scotland", "country": "United Kingdom", "lat": 55.9533, "lon": -3.1883, "sqft": 5000, "opening_date": "2020-06-01"},
    {"store_id": "DUB", "name": "Dublin Dark Store", "region": "Leinster", "country": "Ireland", "lat": 53.3498, "lon": -6.2603, "sqft": 4500, "opening_date": "2020-09-01"},
    {"store_id": "AMS", "name": "Amsterdam Dark Store", "region": "North Holland", "country": "Netherlands", "lat": 52.3676, "lon": 4.9041, "sqft": 7000, "opening_date": "2021-01-10"},
    {"store_id": "FAR", "name": "Global Fallback Fulfillment", "region": "N/A", "country": "N/A", "lat": 51.5072, "lon": -0.1276, "sqft": 3000, "opening_date": "2021-05-01"},
]

_EU_COUNTRIES = {
    "Germany", "France", "Netherlands", "Belgium", "Spain", "Switzerland", "Austria",
    "Portugal", "Italy", "Poland", "Denmark", "Sweden", "Finland", "Norway", "Czech Republic",
    "Greece", "Lithuania",
}


def stores_dataframe() -> pd.DataFrame:
    df = pd.DataFrame(STORES)
    df["is_synthetic"] = True
    return df


def _download_raw() -> str:
    if os.path.exists(RAW_XLSX_PATH):
        return RAW_XLSX_PATH
    os.makedirs(RAW_DIR, exist_ok=True)
    resp = requests.get(DATASET_URL, timeout=120)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xlsx_name = next(n for n in zf.namelist() if n.endswith(".xlsx"))
        with zf.open(xlsx_name) as src, open(RAW_XLSX_PATH, "wb") as dst:
            dst.write(src.read())
    return RAW_XLSX_PATH


def _assign_store(country: str, customer_id, invoice: str) -> str:
    if country == "United Kingdom":
        key = str(customer_id) if pd.notna(customer_id) else str(invoice)
        idx = int(hashlib.md5(key.encode()).hexdigest(), 16) % 3
        return ["LON", "MAN", "EDI"][idx]
    if country in ("Ireland", "EIRE"):
        return "DUB"
    if country in _EU_COUNTRIES:
        return "AMS"
    return "FAR"


def extract_transactions() -> pd.DataFrame:
    path = _download_raw()
    df = pd.read_excel(path, sheet_name=SHEET_NAME, engine="openpyxl")
    df = df.rename(columns={"Customer ID": "customer_id", "Invoice": "invoice_no", "StockCode": "stock_code",
                             "Description": "description", "Quantity": "quantity", "InvoiceDate": "invoice_date",
                             "Price": "unit_price", "Country": "country"})
    return df


def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["invoice_no"] = df["invoice_no"].astype(str)
    is_cancelled = df["invoice_no"].str.startswith("C")
    df = df[~is_cancelled]
    df = df[(df["quantity"] > 0) & (df["unit_price"] > 0) & df["stock_code"].notna()]
    df["stock_code"] = df["stock_code"].astype(str)
    df["store_id"] = df.apply(
        lambda r: _assign_store(r["country"], r["customer_id"], r["invoice_no"]), axis=1
    )
    return df


def validate_transactions(df: pd.DataFrame):
    return validate_dataframe(
        df,
        required_columns=["invoice_no", "stock_code", "quantity", "unit_price", "invoice_date", "store_id"],
        not_null_columns=["invoice_no", "stock_code", "store_id"],
        numeric_ranges={"quantity": (1, 100_000), "unit_price": (0.001, 100_000)},
    )


def build_products(df: pd.DataFrame) -> pd.DataFrame:
    products = (
        df.groupby("stock_code")
        .agg(description=("description", lambda s: s.mode().iat[0] if not s.mode().empty else s.iloc[0]),
             reference_unit_price=("unit_price", "median"))
        .reset_index()
    )
    return products


def build_orders(df: pd.DataFrame) -> pd.DataFrame:
    orders = (
        df.groupby("invoice_no")
        .agg(store_id=("store_id", "first"), order_date=("invoice_date", "min"),
             customer_id=("customer_id", "first"), country=("country", "first"))
        .reset_index()
    )
    orders["order_date"] = pd.to_datetime(orders["order_date"])
    orders["customer_id"] = orders["customer_id"].astype("Int64").astype(str)
    return orders


def build_order_items(df: pd.DataFrame) -> pd.DataFrame:
    items = (
        df.groupby(["invoice_no", "stock_code", "store_id"])
        .agg(quantity=("quantity", "sum"), unit_price=("unit_price", "first"), order_date=("invoice_date", "min"))
        .reset_index()
    )
    items["revenue"] = (items["quantity"] * items["unit_price"]).round(2)
    items["order_date"] = pd.to_datetime(items["order_date"]).dt.date
    return items


def simulate_inventory(order_items: pd.DataFrame) -> pd.DataFrame:
    """Synthetic day-by-day inventory simulation for each (store, top product).

    Starts each store/product at SYNTHETIC_STARTING_STOCK, subtracts that
    day's real observed demand, and restocks back to par whenever stock
    would fall to/below zero (a simple periodic-review policy) -- this
    is the one part of this project invented outright, since the source
    data has no inventory dimension at all. See docs/methodology_dark_store.md.
    """
    top_products = (
        order_items.groupby("stock_code")["quantity"].sum().nlargest(TOP_N_PRODUCTS_FOR_INVENTORY).index
    )
    scoped = order_items[order_items["stock_code"].isin(top_products)].copy()
    scoped["order_date"] = pd.to_datetime(scoped["order_date"])

    daily_demand = (
        scoped.groupby(["store_id", "stock_code", "order_date"])["quantity"].sum().reset_index()
    )

    all_dates = pd.date_range(daily_demand["order_date"].min(), daily_demand["order_date"].max(), freq="D")
    rows = []
    for (store_id, stock_code), grp in daily_demand.groupby(["store_id", "stock_code"]):
        demand_by_date = grp.set_index("order_date")["quantity"].reindex(all_dates, fill_value=0)
        stock = SYNTHETIC_STARTING_STOCK
        for d, demand in demand_by_date.items():
            stock -= int(demand)
            restocked = False
            if stock <= 0:
                stock = SYNTHETIC_RESTOCK_PAR_LEVEL
                restocked = True
            rows.append((store_id, stock_code, d.date(), int(demand), stock, restocked))

    inv = pd.DataFrame(rows, columns=["store_id", "stock_code", "snapshot_date", "units_demanded", "stock_on_hand", "restocked"])
    inv["is_synthetic"] = True
    return inv


def load_stores() -> int:
    return upsert_dataframe(stores_dataframe(), schema="dark_store", table="stores", key_columns=["store_id"])


def load_products(products: pd.DataFrame) -> int:
    return upsert_dataframe(products, schema="dark_store", table="products", key_columns=["stock_code"])


def load_orders(orders: pd.DataFrame) -> int:
    return bulk_upsert_dataframe(orders, schema="dark_store", table="orders", key_columns=["invoice_no"])


def load_order_items(items: pd.DataFrame) -> int:
    return bulk_upsert_dataframe(
        items, schema="dark_store", table="order_items", key_columns=["invoice_no", "stock_code"]
    )


def load_inventory(inv: pd.DataFrame) -> int:
    return bulk_upsert_dataframe(
        inv, schema="dark_store", table="inventory_snapshots", key_columns=["store_id", "stock_code", "snapshot_date"]
    )


def compute_and_load_analytics() -> dict:
    from shared.database import get_engine, run_sql_file

    sql_dir = os.path.join(os.path.dirname(__file__), "sql")
    counts = {}
    for fname, table in [
        ("002_store_daily_metrics.sql", "store_daily_metrics"),
        ("003_inventory_analysis.sql", "inventory_analysis"),
        ("004_store_profitability.sql", "store_profitability"),
        ("005_cross_store_correlation.sql", "cross_store_correlation"),
    ]:
        run_sql_file(os.path.join(sql_dir, fname))
        engine = get_engine()
        with engine.connect() as conn:
            counts[table] = int(conn.exec_driver_sql(f"SELECT COUNT(*) FROM dark_store.{table}").scalar())
    return counts


# --- Demand forecasting -----------------------------------------------------
#
# inventory_snapshots is a genuinely dense store x product x day panel --
# verified live: 327,624 rows, 6 stores, 150 products, 876 distinct
# (store_id, stock_code) pairs, every pair present for all 374 real days
# (2010-12-01 to 2011-12-09). But density is not the same as every
# individual pair being forecastable: 79.1% of individual (store, product,
# day) rows have units_demanded = 0, and the products table has no
# category/family column to fall back on for aggregation. See
# docs/model_card.md for the full reasoning behind the choice below.
DEMAND_MODEL_TEST_START_DATE = "2011-10-15"  # last 56 real days held out
DEMAND_MIN_NONZERO_DAY_FRACTION = 0.4  # density floor, computed on train days only
DEMAND_SEASONAL_LOOKBACK_WEEKS = 4  # seasonal-naive: mean of the last 4 occurrences of that weekday
REORDER_LOOKAHEAD_DAYS = 7  # forecast-informed policy's restock horizon
REORDER_SAFETY_Z = 1.65  # ~95% one-sided service level in the safety-stock formula
DEMAND_NUMERIC_FEATURES = ["lag_1", "lag_7", "rolling_mean_7", "rolling_std_7", "day_of_week", "reference_unit_price"]
DEMAND_CATEGORICAL_FEATURES = ["store_id"]


def _select_demand_pairs() -> pd.DataFrame:
    """(store_id, stock_code) pairs dense enough for daily forecasting to be
    a meaningful exercise -- at least DEMAND_MIN_NONZERO_DAY_FRACTION of
    days with nonzero demand, computed using ONLY the train-period portion
    of the date range. This is a one-time dataset-scoping decision, made
    the same leakage-safe way Fraud/Climate fit their encoders/baselines on
    train data only: never look at the test period to decide it."""
    df = pd.read_sql(
        "SELECT store_id, stock_code, units_demanded FROM dark_store.inventory_snapshots "
        f"WHERE snapshot_date < '{DEMAND_MODEL_TEST_START_DATE}'",
        get_engine(),
    )
    density = df.groupby(["store_id", "stock_code"])["units_demanded"].apply(lambda s: (s > 0).mean())
    dense = density[density >= DEMAND_MIN_NONZERO_DAY_FRACTION]
    return dense.reset_index()[["store_id", "stock_code"]]


def _load_demand_training_frame() -> pd.DataFrame:
    dense_pairs = _select_demand_pairs()
    engine = get_engine()
    snapshots = pd.read_sql(
        "SELECT store_id, stock_code, snapshot_date, units_demanded, stock_on_hand "
        "FROM dark_store.inventory_snapshots",
        engine,
    )
    products = pd.read_sql("SELECT stock_code, reference_unit_price FROM dark_store.products", engine)

    df = dense_pairs.merge(snapshots, on=["store_id", "stock_code"], how="inner")
    df = df.merge(products, on="stock_code", how="left")
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    df["reference_unit_price"] = df["reference_unit_price"].astype(float).fillna(df["reference_unit_price"].median())
    return df.sort_values(["store_id", "stock_code", "snapshot_date"]).reset_index(drop=True)


def build_demand_features(df: pd.DataFrame) -> pd.DataFrame:
    """Lag-1, lag-7, and a trailing 7-day rolling mean/std, all shifted so
    a row never sees its own day's demand -- plus day-of-week, store_id,
    and the product's reference price as static context. The seasonal-naive
    baseline (mean of the last DEMAND_SEASONAL_LOOKBACK_WEEKS occurrences of
    that same weekday) is computed alongside it so model and baseline are
    scored on the identical row set. Rows without enough history yet (the
    first 4 weeks of each pair's series) are dropped -- all fall inside the
    train period, since DEMAND_MODEL_TEST_START_DATE is 318 days into a
    374-day series."""
    df = df.copy()
    df["day_of_week"] = df["snapshot_date"].dt.dayofweek
    pair = df.groupby(["store_id", "stock_code"])["units_demanded"]

    df["lag_1"] = pair.shift(1)
    df["lag_7"] = pair.shift(7)
    df["rolling_mean_7"] = pair.transform(lambda s: s.shift(1).rolling(7).mean())
    df["rolling_std_7"] = pair.transform(lambda s: s.shift(1).rolling(7).std())

    seasonal_lags = [pair.shift(7 * k) for k in range(1, DEMAND_SEASONAL_LOOKBACK_WEEKS + 1)]
    df["seasonal_naive_pred"] = pd.concat(seasonal_lags, axis=1).mean(axis=1)

    required = DEMAND_NUMERIC_FEATURES + ["seasonal_naive_pred"]
    return df.dropna(subset=required).reset_index(drop=True)


def train_demand_model() -> dict:
    """Train an XGBoost regressor on the dense-pair panel to predict daily
    units_demanded, using a day-of-week seasonal-naive baseline as the
    forecasting comparison point (NOT the flat restock-to-300 rule, which
    is evaluated separately in simulate_reorder_policies). Time-based split
    on DEMAND_MODEL_TEST_START_DATE -- never random, since day-of-week and
    trend leakage matters here the same way it did for Fraud and Climate.
    Writes both models' real MAE/RMSE to dark_store.model_evaluation and
    both models' test-set predictions to dark_store.demand_forecast_predictions,
    then runs the reorder-policy comparison and saves evidence images."""
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    from sklearn.preprocessing import OneHotEncoder
    from xgboost import XGBRegressor

    raw = _load_demand_training_frame()
    df = build_demand_features(raw)

    train = df[df["snapshot_date"] < DEMAND_MODEL_TEST_START_DATE].copy()
    test = df[df["snapshot_date"] >= DEMAND_MODEL_TEST_START_DATE].copy()

    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    encoder.fit(train[DEMAND_CATEGORICAL_FEATURES])

    def _encode(split: pd.DataFrame) -> np.ndarray:
        numeric = split[DEMAND_NUMERIC_FEATURES].to_numpy()
        cats = encoder.transform(split[DEMAND_CATEGORICAL_FEATURES])
        return np.hstack([numeric, cats])

    X_train, y_train = _encode(train), train["units_demanded"].to_numpy()
    X_test, y_test = _encode(test), test["units_demanded"].to_numpy()

    model = XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.1, random_state=RNG_SEED, n_jobs=-1)
    model.fit(X_train, y_train)
    model_pred = np.clip(model.predict(X_test), 0, None)
    baseline_pred = test["seasonal_naive_pred"].to_numpy()

    computed_at = datetime.now(timezone.utc)
    metrics = [
        {
            "model_name": "xgboost_demand_model",
            "mae": float(mean_absolute_error(y_test, model_pred)),
            "rmse": float(mean_squared_error(y_test, model_pred) ** 0.5),
            "computed_at": computed_at,
        },
        {
            "model_name": "seasonal_naive_dow",
            "mae": float(mean_absolute_error(y_test, baseline_pred)),
            "rmse": float(mean_squared_error(y_test, baseline_pred) ** 0.5),
            "computed_at": computed_at,
        },
    ]
    upsert_dataframe(pd.DataFrame(metrics), schema="dark_store", table="model_evaluation", key_columns=["model_name"])

    predictions = pd.concat([
        pd.DataFrame({
            "store_id": test["store_id"].to_numpy(), "stock_code": test["stock_code"].to_numpy(),
            "snapshot_date": test["snapshot_date"].dt.date.to_numpy(), "model_name": "xgboost_demand_model",
            "predicted_demand": model_pred, "actual_demand": y_test, "computed_at": computed_at,
        }),
        pd.DataFrame({
            "store_id": test["store_id"].to_numpy(), "stock_code": test["stock_code"].to_numpy(),
            "snapshot_date": test["snapshot_date"].dt.date.to_numpy(), "model_name": "seasonal_naive_dow",
            "predicted_demand": baseline_pred, "actual_demand": y_test, "computed_at": computed_at,
        }),
    ], ignore_index=True)
    bulk_upsert_dataframe(
        predictions, schema="dark_store", table="demand_forecast_predictions",
        key_columns=["store_id", "stock_code", "snapshot_date", "model_name"],
    )

    policy_comparison = simulate_reorder_policies(test, model_pred)
    bulk_upsert_dataframe(
        policy_comparison, schema="dark_store", table="reorder_policy_comparison",
        key_columns=["store_id", "stock_code", "policy_name"],
    )

    save_demand_model_evidence(test=test, model_pred=model_pred, baseline_pred=baseline_pred, metrics=metrics, policy_comparison=policy_comparison)

    return {
        "metrics": metrics,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "dense_pairs": int(df.groupby(["store_id", "stock_code"]).ngroups),
        "policy_comparison": policy_comparison.groupby("policy_name")[["stockout_days", "avg_stock_on_hand"]].mean().to_dict(),
    }


def simulate_reorder_policies(test: pd.DataFrame, model_pred: np.ndarray) -> pd.DataFrame:
    """Replay the real observed test-window demand under two policies for
    each dense pair, both starting from the same real stock level the
    existing simulation had the day before the test window (pulled from
    inventory_snapshots, not reinvented):

      - fixed_restock_300: the existing rule (restock to
        SYNTHETIC_RESTOCK_PAR_LEVEL whenever stock would hit <= 0).
      - forecast_plus_safety_buffer: restock to (this day's XGBoost
        forecast x REORDER_LOOKAHEAD_DAYS) + a z*sigma safety buffer,
        using the pair's own trailing demand std (rolling_std_7) -- same
        <= 0 trigger as the existing rule, so the comparison isolates
        *what to restock to*, not *when to check*.

    Both policies see the identical real demand each day; only the restock
    quantity differs. stockout_days uses the same restocked-day proxy
    definition sql/003_inventory_analysis.sql already uses."""
    test = test.copy()
    test["model_pred"] = model_pred

    start_date = pd.Timestamp(DEMAND_MODEL_TEST_START_DATE) - pd.Timedelta(days=1)
    start_stock = pd.read_sql(
        "SELECT store_id, stock_code, stock_on_hand FROM dark_store.inventory_snapshots WHERE snapshot_date = %(d)s",
        get_engine(), params={"d": start_date.date()},
    ).set_index(["store_id", "stock_code"])["stock_on_hand"]

    rows = []
    for (store_id, stock_code), grp in test.sort_values("snapshot_date").groupby(["store_id", "stock_code"]):
        stock_fixed = int(start_stock.get((store_id, stock_code), SYNTHETIC_RESTOCK_PAR_LEVEL))
        stock_forecast = stock_fixed
        fixed_stockouts = forecast_stockouts = 0
        fixed_levels, forecast_levels = [], []

        for _, r in grp.iterrows():
            demand = int(r["units_demanded"])

            stock_fixed -= demand
            if stock_fixed <= 0:
                stock_fixed = SYNTHETIC_RESTOCK_PAR_LEVEL
                fixed_stockouts += 1
            fixed_levels.append(stock_fixed)

            stock_forecast -= demand
            if stock_forecast <= 0:
                sigma = float(r["rolling_std_7"]) if pd.notna(r["rolling_std_7"]) else 0.0
                restock_to = max(0, round(
                    r["model_pred"] * REORDER_LOOKAHEAD_DAYS + REORDER_SAFETY_Z * sigma * (REORDER_LOOKAHEAD_DAYS ** 0.5)
                ))
                stock_forecast = restock_to
                forecast_stockouts += 1
            forecast_levels.append(stock_forecast)

        rows.append({"store_id": store_id, "stock_code": stock_code, "policy_name": "fixed_restock_300",
                     "stockout_days": fixed_stockouts, "avg_stock_on_hand": float(np.mean(fixed_levels))})
        rows.append({"store_id": store_id, "stock_code": stock_code, "policy_name": "forecast_plus_safety_buffer",
                     "stockout_days": forecast_stockouts, "avg_stock_on_hand": float(np.mean(forecast_levels))})

    result = pd.DataFrame(rows)
    result["computed_at"] = datetime.now(timezone.utc)
    return result


def save_demand_model_evidence(
    *, test: pd.DataFrame, model_pred: np.ndarray, baseline_pred: np.ndarray, metrics: list[dict],
    policy_comparison: pd.DataFrame,
) -> None:
    """Forecast-vs-actual time series for the busiest dense pair, an
    MAE comparison bar chart, and the reorder-policy comparison -- real
    images from this actual run, not mocked."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    test = test.copy()
    test["model_pred"] = model_pred
    test["baseline_pred"] = baseline_pred

    sample_pair = test.groupby(["store_id", "stock_code"])["units_demanded"].sum().idxmax()
    sample = test[(test["store_id"] == sample_pair[0]) & (test["stock_code"] == sample_pair[1])].sort_values("snapshot_date")

    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(sample["snapshot_date"], sample["units_demanded"], label="actual", color="#333333", linewidth=1.5)
    ax.plot(sample["snapshot_date"], sample["model_pred"], label="xgboost_demand_model", color="#2a6f97", alpha=0.85)
    ax.plot(sample["snapshot_date"], sample["baseline_pred"], label="seasonal_naive_dow", color="#e07a5f", alpha=0.85, linestyle="--")
    ax.set_title(f"Forecast vs. actual, held-out test period -- {sample_pair[0]}/{sample_pair[1]} (busiest dense pair)")
    ax.set_ylabel("units_demanded")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(EVIDENCE_DIR, "dark_store_forecast_vs_actual.png"), dpi=150)
    plt.close(fig)

    by_name = {m["model_name"]: m for m in metrics}
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    names = list(by_name.keys())
    axes[0].bar(names, [by_name[n]["mae"] for n in names], color=["#2a6f97", "#e07a5f"])
    axes[0].set_title("MAE on held-out days (lower is better)")
    axes[0].tick_params(axis="x", rotation=15)
    axes[1].bar(names, [by_name[n]["rmse"] for n in names], color=["#2a6f97", "#e07a5f"])
    axes[1].set_title("RMSE on held-out days (lower is better)")
    axes[1].tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(os.path.join(EVIDENCE_DIR, "dark_store_mae_rmse_comparison.png"), dpi=150)
    plt.close(fig)

    policy_summary = policy_comparison.groupby("policy_name").agg(
        total_stockout_days=("stockout_days", "sum"), avg_stock_on_hand=("avg_stock_on_hand", "mean"),
    ).reindex(["fixed_restock_300", "forecast_plus_safety_buffer"])

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    axes[0].bar(policy_summary.index, policy_summary["total_stockout_days"], color=["#e07a5f", "#2a6f97"])
    axes[0].set_title(f"Total stockout-proxy days across {len(policy_comparison)//2} pairs\n(held-out test window, lower is better)")
    axes[0].tick_params(axis="x", rotation=15)
    axes[1].bar(policy_summary.index, policy_summary["avg_stock_on_hand"], color=["#e07a5f", "#2a6f97"])
    axes[1].set_title("Average inventory held per pair\n(held-out test window)")
    axes[1].tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(os.path.join(EVIDENCE_DIR, "dark_store_reorder_policy_comparison.png"), dpi=150)
    plt.close(fig)

    # The pair-equal-weighted MEAN above makes the two policies look like a
    # wash on inventory held -- but that hides a real split: most pairs hold
    # meaningfully LESS inventory under the forecast policy, while a handful
    # of highly volatile pairs get a very large sqrt(lead-time) safety
    # buffer and balloon upward, dragging the simple mean back up. This
    # scatter shows every pair instead of collapsing them into one number.
    wide = policy_comparison.pivot(index=["store_id", "stock_code"], columns="policy_name", values="avg_stock_on_hand")
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    ax.scatter(wide["fixed_restock_300"], wide["forecast_plus_safety_buffer"], alpha=0.6, color="#2a6f97")
    lim = float(max(wide.max().max(), 1) * 1.05)
    ax.plot([0, lim], [0, lim], "k--", alpha=0.3, label="equal")
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("avg_stock_on_hand -- fixed_restock_300")
    ax.set_ylabel("avg_stock_on_hand -- forecast_plus_safety_buffer")
    below = int((wide["forecast_plus_safety_buffer"] < wide["fixed_restock_300"]).sum())
    ax.set_title(f"Per-pair inventory held, one dot per pair\n{below} of {len(wide)} pairs fall below the line (hold less)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(EVIDENCE_DIR, "dark_store_reorder_stock_scatter.png"), dpi=150)
    plt.close(fig)
