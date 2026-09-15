# Data Sources

## Transactions — real, keyless

**UCI Machine Learning Repository, "Online Retail II"**
(`https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip`) — ~541,000 real
transaction line items from a UK-based online retailer, Dec 2010-Dec 2011. No API key required
(verified live, direct HTTPS download). License: CC BY 4.0. Only the "Year 2010-2011" sheet is
used, to keep ingestion time reasonable.

This is real transaction data, but it has **no store, location, inventory, or cost dimension at
all** — it's a single online retailer's order log.

## Store network, inventory, costs — synthetic

To make the real order log analyzable as a multi-location fulfillment network:
- each order is **deterministically** assigned to one of 6 dark stores based on the customer's
  real country field (simulating which warehouse would have shipped it)
- store metadata (address, sqft, opening date) is synthetic
- inventory levels are simulated day-by-day from each store's real observed demand for its top
  products (a simple periodic-review policy — not measured stock)
- unit cost / opex assumptions used for profitability are synthetic illustrative figures

All flagged `is_synthetic = true` in the relevant tables. No API key required anywhere in this
pipeline.
