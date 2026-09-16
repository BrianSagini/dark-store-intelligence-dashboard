# Dark Store Intelligence Dashboard

The UCI "Online Retail II" dataset is real — about 541,000 line items from a UK online retailer
across 2010–2011 — but it's a single retailer's order log with no store, location, or inventory
dimension at all. I built the rest: a deterministic routing rule that assigns every order to one
of 6 fulfillment "dark stores" by country, a day-by-day inventory simulation running on top of the
real observed demand, and cost assumptions to turn revenue into estimated profitability. The
result is a full retail-operations dashboard where the demand signal is real and everything about
the store network on top of it is a documented, clearly-flagged construction.

This is one of four projects in a portfolio built around the same stack, different problem each
time — see [the rest of it](#the-rest-of-the-portfolio) at the bottom.

**Stack**: Airflow 3.3.1 → PostgreSQL 16 → Python/SQL → Streamlit + Plotly → Power BI.

## Running it

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> AIRFLOW_FERNET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"                                 # -> AIRFLOW_JWT_SECRET
# paste both into .env

docker compose up -d --build
docker compose ps
```

```bash
docker compose exec airflow-scheduler airflow dags unpause dark_store_pipeline
docker compose exec airflow-scheduler airflow dags trigger dark_store_pipeline
```

Airflow's at http://localhost:8081, dashboard at http://localhost:8501 once the run finishes.
Budget 30–40 minutes for the first run — most of that is parsing the real ~45MB/541k-row
spreadsheet, everything after it is fast, and it's cached locally so reruns don't re-download it.
`docker compose down` when you're done, without losing data.

## How the pipeline is put together

Check the source is reachable → ensure schema → load store metadata → extract and clean the UCI
spreadsheet → validate → build products/orders/order-items → run the inventory simulation →
compute daily metrics, inventory health, profitability, and cross-store correlation in SQL →
build the Power BI views → a data-quality check at the end. Every table keys on something natural
so a rerun upserts instead of duplicating.

## What's real and what I built

Revenue, orders, and units sold are real numbers from real transactions. Inventory levels, unit
costs, and profitability are estimates on top of documented, simple assumptions (start each
product at 300 units per store, subtract real daily demand, restock to 300 the instant it would
hit zero; COGS at 42% of revenue, opex at $4/sqft/month) — not measured facts, and I don't
pretend otherwise anywhere in the schema or the dashboard.

The one I'd flag specifically: the dashboard has a cross-store revenue correlation view, but I
built the store assignment as a deterministic, non-overlapping function of each order's country —
no two stores ever compete for the same customer, so there's no real overlapping catchment area to
test cannibalization against. The correlation view shows something real (how much two stores'
demand trends move together, e.g. riding the same seasonal cycle) but it isn't cannibalization
evidence, and I say so directly rather than let the chart imply more than it supports. Full
writeup: `docs/methodology.md`.

## Power BI

Hand-built semantic model — 4 tables (including a genuine `Stores` dimension, not just a fact
table), 3 relationships, 8 DAX measures — behind a 4-page, 23-visual report. I opened every page
in Power BI Desktop myself and confirmed it renders correctly with real data before calling it
done; screenshots are in `docs/evidence/`. Full page layout, the color system, and the design
reasoning are in `docs/powerbi_guide.md`.

## Docs

`docs/methodology.md`, `docs/powerbi_guide.md`, `docs/database_schema.md`, `docs/data_sources.md`.

## The rest of the portfolio

Climate Risk & Business Impact, AI Hiring Bias Detector, Fraud Pattern Evolution Tracker — same
stack, each its own self-contained repo.
