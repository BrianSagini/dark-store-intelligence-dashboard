# Project 2 — Dark Store Intelligence: Methodology & Limitations

## Data

- **Real**: UCI "Online Retail II" dataset, `Year 2010-2011` sheet — ~541k real transaction line
  items from a UK-based online retailer (Dec 2010–Dec 2011). Columns used: `Invoice`, `StockCode`,
  `Description`, `Quantity`, `InvoiceDate`, `Price`, `Customer ID`, `Country`. Cancelled invoices
  (`Invoice` starting with `C`) and non-positive quantity/price rows are excluded before loading.
- **Synthetic**: this dataset has no store, location, or inventory dimension at all — it is a single
  retailer's order log. Everything below is invented to make it analyzable as a multi-location
  "dark store" fulfillment network, and is flagged `is_synthetic[_business_data]` in the schema:
  - **Store assignment**: each order is deterministically routed to one of 6 fulfillment centers
    based on the order's real `Country` field: UK orders go to one of 3 UK stores (chosen by a hash
    of `Customer ID`, so a given customer always routes to the same store), Ireland/EIRE orders go
    to Dublin, other EU-country orders go to Amsterdam, everything else to a global fallback store.
  - **Store metadata** (address, sqft, opening date) is invented.
  - **Inventory** (`dark_store.inventory_snapshots`) is a day-by-day simulation for each store's
    top 150 products by volume: start at 300 units, subtract that day's *real* observed demand,
    and instantly restock to 300 whenever supply would hit zero. There is no real inventory data
    to draw on — this is a simple periodic-review-policy simulation, not a fitted model.
  - **Cost assumptions**: COGS = 42% of revenue, opex = $4/sqft/month — both illustrative
    placeholders, not sourced from any real retailer's P&L.

## Analytical models (SQL, `sql/002`–`005`)

- `store_daily_metrics`: real revenue/orders/units per store per day.
- `inventory_analysis`: avg daily demand, avg stock on hand, days of supply, turnover ratio (all
  from the synthetic simulation), and `stockout_days` — because the simulation restocks the
  *same day* stock would hit zero (no lead-time lag), stored stock is never actually ≤0, so
  `stockout_days` counts restock-triggered days as a stockout *proxy*, not an observed stockout.
- `store_profitability`: monthly revenue (real) minus the synthetic COGS/opex assumptions above.
- `cross_store_correlation`: weekly revenue correlation between every store pair.

## What "cannibalization analysis" means here (important limitation)

The prompt driving this portfolio asked for cannibalization analysis "where supported by the
data." Store assignment here is a **deterministic, non-overlapping** function of each order's
country/customer — no two stores ever compete for the same customer's order, so there is no real
overlapping catchment area to test whether one store's growth comes at another's expense.
`cross_store_correlation` is offered instead as a **weaker, different signal**: how correlated two
stores' overall demand trends are (e.g., both riding the same seasonal retail cycle). High
correlation there should **not** be read as evidence of demand shifting between stores — that
would require real geographic overlap this dataset doesn't have.

## What this project does *not* do

- Does not reflect any real company's actual store network, inventory, or financials.
- Does not model lead times, supplier constraints, or safety stock policy beyond the simple
  restock-to-par rule above.
- Does not attempt real cannibalization/catchment-area analysis (see above).
