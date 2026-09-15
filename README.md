# 📦 Dark Store Intelligence Dashboard

An end-to-end retail/fulfillment analytics pipeline: real e-commerce transactions reshaped into a
6-store "dark store" fulfillment network, with inventory simulation and profitability analysis.
Part of a 4-project data analytics portfolio ([siblings](#related-projects) below); this repo is
fully self-contained and runs on its own.

**Stack**: Apache Airflow 3.3.1 → PostgreSQL 16 → Python/SQL → Streamlit + Plotly → Power BI
(`.pbip` project included, unvalidated — see [Power BI](#power-bi)).

## Data

- **Real**: ~541,000 real transaction line items from the UCI "Online Retail II" dataset (UK-based
  online retailer, Dec 2010-Dec 2011) — keyless direct download, CC BY 4.0.
- **Synthetic**: this real order log has no store/location/inventory/cost dimension at all, so
  each order is deterministically assigned to one of 6 fulfillment "dark stores" (by customer
  country), store metadata is synthetic, inventory is simulated day-by-day from real observed
  demand, and unit-cost/opex assumptions are synthetic. Every synthetic table/column is flagged.

Full sourcing, licensing, and methodology detail: `docs/methodology.md`.

## Quick start

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> AIRFLOW_FERNET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"                                 # -> AIRFLOW_JWT_SECRET
# paste both into .env

docker compose up -d --build
docker compose ps
```

Airflow UI: http://localhost:8081.

```bash
docker compose exec airflow-scheduler airflow dags unpause dark_store_pipeline
docker compose exec airflow-scheduler airflow dags trigger dark_store_pipeline
```

Dashboard: http://localhost:8501 once the DAG completes — **this one takes ~30-40 minutes**,
dominated by parsing the real ~45MB/541k-row spreadsheet; everything downstream is fast.

Shut down (keeps data): `docker compose down`.

## Pipeline

`dark_store_pipeline` DAG: check source → ensure schema → load store metadata → extract & clean
the UCI spreadsheet → validate → build products/orders/order-items → simulate inventory → compute
daily metrics, inventory health, profitability, and cross-store correlation (SQL) → build Power BI
views → data-quality check. Idempotent — reruns upsert on natural keys, never duplicate; the raw
spreadsheet is cached locally after first download so reruns don't re-fetch it.

## What the numbers mean

Revenue/orders/units are real. Inventory levels, costs, and profitability are estimates built on
documented, simple assumptions — not measured facts. Cross-store revenue correlation is an
explicit **proxy**, not evidence of demand cannibalization between stores (the synthetic store
assignment doesn't create real overlapping catchment areas). Full detail: `docs/methodology.md`.

## Power BI

A real `.pbip` project (`powerbi/DarkStoreIntelligence.pbip`) exists with the complete data model
— 4 tables (including a genuine `Stores` dimension), 3 relationships, 8 DAX measures — but **it
has never been opened in Power BI Desktop, so it isn't validated.** The 4 report pages exist but
have no visuals yet. See `docs/powerbi_guide.md` for exact build instructions if you open it and
it needs finishing.

## Documentation

`docs/methodology.md` · `docs/powerbi_guide.md` · `docs/database_schema.md` · `docs/data_sources.md`.

## Related projects

Part of a 4-project portfolio, each in its own self-contained repo: Climate Risk & Business
Impact, AI Hiring Bias Detector, Fraud Pattern Evolution Tracker.
