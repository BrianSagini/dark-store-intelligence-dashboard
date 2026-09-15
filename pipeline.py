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
from datetime import timedelta

import pandas as pd
import requests

from shared.database import bulk_upsert_dataframe, upsert_dataframe
from shared.validation import validate_dataframe

DATASET_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
SHEET_NAME = "Year 2010-2011"
RAW_DIR = os.path.join(os.path.dirname(__file__), "data_raw")
RAW_XLSX_PATH = os.path.join(RAW_DIR, "online_retail_II.xlsx")
TOP_N_PRODUCTS_FOR_INVENTORY = 150
SYNTHETIC_STARTING_STOCK = 300
SYNTHETIC_RESTOCK_PAR_LEVEL = 300
SYNTHETIC_COGS_RATE = 0.42  # illustrative: cost of goods as a fraction of unit price

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
