"""Dark Store Intelligence -- Streamlit dashboard.

Reads only from dark_store.* via the read-only ANALYTICS_DATABASE_URL
connection. Real order data drives revenue/demand; inventory, cost, and
profitability figures rest on documented synthetic assumptions -- see
docs/methodology_dark_store.md.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import text

from shared.database import get_engine

st.set_page_config(page_title="Dark Store Intelligence", layout="wide")
st.title("📦 Dark Store Intelligence Dashboard")
st.caption(
    "Real transactions from the UCI 'Online Retail II' dataset. Store "
    "assignment, inventory levels, and cost/profitability assumptions are "
    "**synthetic** -- see docs/methodology_dark_store.md, including why "
    "cross-store correlation is a weaker proxy, not real cannibalization analysis."
)


@st.cache_data(ttl=300)
def load(query: str) -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(text(query), engine)


try:
    stores = load("SELECT * FROM dark_store.stores ORDER BY name")
    daily = load("SELECT * FROM dark_store.store_daily_metrics ORDER BY metric_date")
    inventory = load(
        "SELECT ia.*, s.name FROM dark_store.inventory_analysis ia JOIN dark_store.stores s ON s.store_id = ia.store_id"
    )
    profitability = load(
        "SELECT p.*, s.name FROM dark_store.store_profitability p JOIN dark_store.stores s ON s.store_id = p.store_id ORDER BY month"
    )
    correlation = load(
        "SELECT c.*, sa.name AS name_a, sb.name AS name_b FROM dark_store.cross_store_correlation c "
        "JOIN dark_store.stores sa ON sa.store_id = c.store_id_a JOIN dark_store.stores sb ON sb.store_id = c.store_id_b"
    )
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not connect to the analytics database: {exc}")
    st.stop()

if stores.empty or daily.empty:
    st.warning(
        "No data yet. Trigger the `dark_store_pipeline` DAG in Airflow "
        "(http://localhost:8081) and wait for it to complete, then refresh."
    )
    st.stop()

daily = daily.merge(stores[["store_id", "name"]], on="store_id")
selected = st.multiselect("Stores", options=stores["name"].tolist(), default=stores["name"].tolist())
daily_f = daily[daily["name"].isin(selected)]

col1, col2, col3 = st.columns(3)
col1.metric("Total revenue", f"${daily_f['revenue'].sum():,.0f}")
col2.metric("Total orders", f"{int(daily_f['orders_count'].sum()):,}")
col3.metric("Stores", len(stores))

st.subheader("Store locations")
fig_map = px.scatter_geo(
    stores, lat="lat", lon="lon", hover_name="name", size=[20] * len(stores),
    projection="natural earth", title="Dark store fulfillment network",
)
st.plotly_chart(fig_map, use_container_width=True)

st.subheader("Daily revenue by store")
daily_f["metric_date"] = pd.to_datetime(daily_f["metric_date"])
weekly = daily_f.set_index("metric_date").groupby("name").resample("W")["revenue"].sum().reset_index()
fig_rev = px.line(weekly, x="metric_date", y="revenue", color="name", title="Weekly revenue by store")
st.plotly_chart(fig_rev, use_container_width=True)

st.subheader("Inventory health (top 150 products per store)")
inv_summary = inventory.groupby("name").agg(
    avg_days_of_supply=("days_of_supply", "mean"),
    total_stockout_days=("stockout_days", "sum"),
    avg_turnover=("turnover_ratio", "mean"),
).reset_index()
st.dataframe(
    inv_summary.rename(columns={
        "name": "Store", "avg_days_of_supply": "Avg days of supply",
        "total_stockout_days": "Total stockout events", "avg_turnover": "Avg turnover ratio (annualized)",
    }).round(1),
    use_container_width=True, hide_index=True,
)

worst_inventory = inventory.sort_values("stockout_days", ascending=False).head(10)
fig_inv = px.bar(
    worst_inventory, x="stock_code", y="stockout_days", color="name",
    title="Top 10 products by stockout events (any store)",
)
st.plotly_chart(fig_inv, use_container_width=True)

st.subheader("Store profitability")
month_options = sorted(profitability["month"].unique(), reverse=True)
if month_options:
    latest_month = st.selectbox("Month", options=month_options, index=0)
    prof_month = profitability[profitability["month"] == latest_month].sort_values("profit_estimate", ascending=False)
    fig_prof = px.bar(prof_month, x="name", y="profit_estimate", color="name", title=f"Estimated profit, {latest_month}")
    st.plotly_chart(fig_prof, use_container_width=True)
    st.dataframe(
        prof_month[["name", "revenue", "cogs_estimate", "opex_estimate", "profit_estimate", "roi_pct"]]
        .rename(columns={"name": "Store", "revenue": "Revenue", "cogs_estimate": "COGS (est.)",
                          "opex_estimate": "Opex (est.)", "profit_estimate": "Profit (est.)", "roi_pct": "ROI %"}),
        use_container_width=True, hide_index=True,
    )

with st.expander("Cross-store weekly revenue correlation (proxy, not cannibalization)"):
    st.dataframe(
        correlation[["name_a", "name_b", "weekly_revenue_correlation"]]
        .rename(columns={"name_a": "Store A", "name_b": "Store B", "weekly_revenue_correlation": "Correlation"})
        .round(3),
        use_container_width=True, hide_index=True,
    )
    st.caption(
        "High correlation here means two stores' overall demand trends move together "
        "(e.g. shared seasonality) -- it is NOT evidence of demand shifting between "
        "stores. See docs/methodology_dark_store.md."
    )

with st.expander("Methodology & limitations"):
    st.markdown(
        """
        - **Revenue/orders/units** are real (UCI Online Retail II).
        - **Store assignment, inventory levels, and cost assumptions are synthetic** -- see
          `docs/methodology_dark_store.md` for exact formulas and why cross-store correlation
          is a proxy, not a cannibalization measurement.
        """
    )
