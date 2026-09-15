"""Dark Store Intelligence -- Airflow DAG.

Real UCI "Online Retail II" transactions -> synthetic store assignment ->
synthetic inventory simulation -> SQL analytics (daily metrics, inventory
health, profitability, cross-store correlation) -> data-quality check.

See projects/02_dark_store_intelligence/pipeline.py and
docs/methodology_dark_store.md for what's real vs. synthetic here.
"""
from __future__ import annotations

import os
import tempfile
from datetime import timedelta

import pandas as pd
import pendulum
import requests
from airflow.sdk import DAG, task

import pipeline
from shared.database import get_engine

TMP = tempfile.gettempdir()

with DAG(
    dag_id="dark_store_pipeline",
    description="Ingest UCI Online Retail II, simulate dark-store fulfillment, compute inventory/profitability analytics",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
        "execution_timeout": timedelta(minutes=45),
    },
    tags=["retail", "project-02"],
) as dag:

    @task
    def check_source_available() -> bool:
        resp = requests.head(
            "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip", timeout=30, allow_redirects=True
        )
        resp.raise_for_status()
        return True

    @task
    def ensure_schema() -> None:
        from shared.database import run_sql_file
        run_sql_file(os.path.join(os.path.dirname(pipeline.__file__), "sql", "001_schema.sql"))

    @task
    def load_stores() -> int:
        return pipeline.load_stores()

    @task
    def extract_and_clean() -> str:
        raw = pipeline.extract_transactions()
        clean = pipeline.clean_transactions(raw)
        path = os.path.join(TMP, "dark_store_transactions.parquet")
        clean.to_parquet(path)
        return path

    @task
    def validate(clean_path: str) -> str:
        df = pd.read_parquet(clean_path)
        report = pipeline.validate_transactions(df)
        report.raise_if_invalid(max_invalid_ratio=0.02)
        clean_df = df.drop(index=list(report.invalid_row_indices))
        path = os.path.join(TMP, "dark_store_validated.parquet")
        clean_df.to_parquet(path)
        return path

    @task
    def build_and_load_products(validated_path: str) -> int:
        df = pd.read_parquet(validated_path)
        return pipeline.load_products(pipeline.build_products(df))

    @task
    def build_and_load_orders(validated_path: str) -> int:
        df = pd.read_parquet(validated_path)
        return pipeline.load_orders(pipeline.build_orders(df))

    @task
    def build_order_items(validated_path: str) -> str:
        df = pd.read_parquet(validated_path)
        items = pipeline.build_order_items(df)
        path = os.path.join(TMP, "dark_store_order_items.parquet")
        items.to_parquet(path)
        return path

    @task
    def load_order_items_task(items_path: str) -> int:
        items = pd.read_parquet(items_path)
        return pipeline.load_order_items(items)

    @task
    def simulate_and_load_inventory(items_path: str) -> int:
        items = pd.read_parquet(items_path)
        inv = pipeline.simulate_inventory(items)
        return pipeline.load_inventory(inv)

    @task
    def compute_analytics(_order_items_loaded: int, _inventory_loaded: int) -> dict:
        return pipeline.compute_and_load_analytics()

    @task
    def create_powerbi_views(_analytics: dict) -> None:
        from shared.database import run_sql_file
        run_sql_file(os.path.join(os.path.dirname(pipeline.__file__), "sql", "006_powerbi_views.sql"))

    @task
    def data_quality_check(_views_done: None) -> None:
        engine = get_engine()
        with engine.connect() as conn:
            orphan_items = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM dark_store.order_items oi "
                "LEFT JOIN dark_store.orders o ON o.invoice_no = oi.invoice_no WHERE o.invoice_no IS NULL"
            ).scalar()
            negative_revenue = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM dark_store.store_daily_metrics WHERE revenue < 0"
            ).scalar()
        if orphan_items:
            raise ValueError(f"{orphan_items} order_items reference a missing order")
        if negative_revenue:
            raise ValueError(f"{negative_revenue} store_daily_metrics rows have negative revenue")

    src_ok = check_source_available()
    schema = ensure_schema()
    stores = load_stores()
    clean_path = extract_and_clean()
    validated_path = validate(clean_path)
    products = build_and_load_products(validated_path)
    orders = build_and_load_orders(validated_path)
    items_path = build_order_items(validated_path)
    items_loaded = load_order_items_task(items_path)
    inv_loaded = simulate_and_load_inventory(items_path)
    analytics = compute_analytics(items_loaded, inv_loaded)
    views = create_powerbi_views(analytics)
    dq = data_quality_check(views)

    src_ok >> schema
    schema >> [stores, clean_path]
    stores >> orders
    stores >> items_loaded
    stores >> inv_loaded
    validated_path >> [products, orders]
    products >> items_loaded
    products >> inv_loaded
    orders >> items_loaded
