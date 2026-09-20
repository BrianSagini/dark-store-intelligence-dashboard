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

Airflow's at http://localhost:8081. Live public dashboard: https://dark-store-intelligence.streamlit.app/
(reads from a shared cloud database, not this local stack) -- your own local run's dashboard is at
http://localhost:8501 once the run finishes. Live H2O AutoML results:
https://dark-store-automl.streamlit.app/ (also reads from the shared cloud database). Budget 30–40 minutes for the first run — most of that is parsing the real ~45MB/541k-row
spreadsheet, everything after it is fast, and it's cached locally so reruns don't re-download it.
`docker compose down` when you're done, without losing data.

The AutoML sanity-check cells at the end of `demand_forecast_model.ipynb` are optional and
local-only — they're not part of the Airflow DAG or the container image. Running them needs
`pip install -r requirements-notebooks.txt` in a local virtualenv plus a JVM on your machine (H2O
starts its own local Java process); skip that cell block entirely if you don't have Java installed.

## How the pipeline is put together

Check the source is reachable → ensure schema → load store metadata → extract and clean the UCI
spreadsheet → validate → build products/orders/order-items → run the inventory simulation →
compute daily metrics, inventory health, profitability, and cross-store correlation in SQL →
train the demand-forecasting model → build the Power BI views → a data-quality check at the end.
Every table keys on something natural so a rerun upserts instead of duplicating.

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

## Machine learning

`inventory_snapshots` is a genuinely dense panel — 327,624 rows, every one of 876 `(store, product)`
pairs present for all 374 real days — but density isn't the same as every pair being forecastable:
79.1% of individual `(store, product, day)` rows have zero demand, and `products` has no
category/family column to fall back on for aggregation. Rather than invent a grouping the schema
doesn't support, I scoped the forecasting exercise to the 152 pairs with at least 40% nonzero-demand
days (checked on train data only, to keep the scoping decision itself leakage-free). That surfaced a
real finding I hadn't assumed going in: those 152 pairs are almost entirely from 3 of the 6 stores
(LON, EDI, MAN) — the store-assignment logic routes the bulk of this real UK-heavy dataset across
only those three, leaving Dublin, Amsterdam, and the fallback store too thin on any single product
to forecast daily. Full reasoning: `docs/model_card.md`.

I trained an XGBoost regressor (lag-1, lag-7, a trailing 7-day rolling mean/std, day-of-week, price,
store) on a time-based split (train on everything before Oct 15 2011, test on the last 56 real
days) against a day-of-week seasonal-naive baseline — the mean of that pair's demand on the same
weekday over the trailing 4 weeks.

| Model | MAE | RMSE |
|---|---|---|
| XGBoost | **17.97** | 68.99 |
| Seasonal-naive (day-of-week) | 19.25 | **68.91** |

A mixed result: XGBoost wins on MAE by about 6.6%, loses narrowly on RMSE (within 0.1%, essentially
tied). The busiest pair in this set has days spiking to 1,000–2,900 units against a typical day
under 100 — neither model anticipates those, and RMSE (which squares errors) is dominated by those
rare misses about equally for both; MAE reflects the much more common small days, where XGBoost's
lag features give it a real edge.

**The part that actually matters for a store network**: I used the forecasts to simulate an
alternative reorder policy — restock to `(forecast × 7 days) + a 1.65σ safety buffer` instead of the
existing flat restock-to-300 — replayed over the same real held-out demand, same starting stock, same
"restock when it hits zero" trigger as the existing rule. Taken as a single pair-averaged number, it
looks like a wash: slightly more stockout-proxy days (2.89 vs. 2.25 per pair) for about the same
average inventory held (164 vs. 165). I didn't stop at that headline number, because it turned out to
hide something real: **the median pair's inventory dropped by 34 units and 71% of pairs (108 of 152)
held less inventory** — a genuine capital-efficiency win for a typical product — but a handful of
highly volatile, high-volume pairs (one goes from 181 to 1,632 average units held) get a very large
safety buffer that single-handedly drags the simple average back up to a wash. That's not "the model
doesn't help" — it's a specific, fixable gap (the safety-stock formula needs a cap for high-variance
products before this policy should run uniformly), and I'd rather report the real mechanism than
either the flattering median or the unflattering mean on its own. Full breakdown, including the
per-pair scatter that makes this visible: `docs/model_card.md`.

This training and simulation run is a real Airflow task (`train_demand_model`, wired into
`dark_store_pipeline` right after the existing analytics step), not a notebook run in isolation — it
writes both models' metrics to `dark_store.model_evaluation`, held-out predictions to
`dark_store.demand_forecast_predictions`, and the full reorder-policy comparison to
`dark_store.reorder_policy_comparison`. `demand_forecast_model.ipynb` is the same analysis end to
end, calling the exact same `pipeline.py` functions the DAG does. Forecast-vs-actual, the MAE/RMSE
comparison, and the reorder-policy scatter are real images from this exact run, in `docs/evidence/`.

## Power BI

Hand-built semantic model — 4 tables (including a genuine `Stores` dimension, not just a fact
table), 3 relationships, 8 DAX measures — behind a 4-page, 23-visual report. I opened every page
in Power BI Desktop myself and confirmed it renders correctly with real data before calling it
done; screenshots are in `docs/evidence/`. Full page layout, the color system, and the design
reasoning are in `docs/powerbi_guide.md`.

## Docs

`docs/methodology.md`, `docs/model_card.md` (the demand model and reorder-policy comparison),
`docs/powerbi_guide.md`, `docs/database_schema.md`, `docs/data_sources.md`.

## The rest of the portfolio

Climate Risk & Business Impact, AI Hiring Bias Detector, Fraud Pattern Evolution Tracker — same
stack, each its own self-contained repo.
