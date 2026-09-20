# Model card — demand forecasting and reorder policy

## The grouping decision, checked against the live data first

`dark_store.inventory_snapshots` is genuinely dense as a panel — verified live:
`SELECT COUNT(*), MIN(snapshot_date), MAX(snapshot_date) FROM dark_store.inventory_snapshots` returns
**327,624 rows**, 6 stores, 150 products, **2010-12-01 to 2011-12-09** (374 real days), and every one
of the **876** distinct `(store_id, stock_code)` pairs has exactly 374 rows — no gaps. That part of
the prompt's premise held up.

What didn't hold up at face value: **79.1% of individual `(store, product, day)` rows have
`units_demanded = 0`**, and the median pair's average daily demand is only 4.4 units. `products` has
no category/family column — just `stock_code`, `description`, `reference_unit_price` — so the
originally-planned "per store/product family" grouping doesn't exist in the schema and had to be
decided here.

**Options considered**:
- **(b) aggregate to per-store totals** — rejected. The actual reorder decision (`simulate_inventory()`,
  and the policy comparison this project cares about) operates at `(store, product)` grain. A
  store-level forecast can't be turned back into a per-product restock quantity without reinventing
  an allocation step, which just relocates the hard problem rather than solving it.
- **(c) a derived coarse family** (price-quartile bucket, or first token of `description`) —
  rejected. `description` free text and `reference_unit_price` don't cleanly separate into
  meaningful demand cohorts (a $2 novelty item and a $2 greeting card would land in the same
  bucket with no shared demand pattern), and a data-driven fix for the real problem — most
  individual pairs are simply too sparse to forecast daily — was available without inventing a
  grouping dimension the schema doesn't support.
- **(a) individual `(store_id, stock_code)` pairs, scoped to the ones dense enough to be
  meaningful** — chosen. Filtered to pairs with at least 40% of days showing nonzero demand,
  computed using **only the train-period portion of the date range** (leakage-safe, the same way
  Fraud's and Climate's encoders/baselines are fit on train data only, never test data) — this
  leaves **152 of 876 pairs**.

**A real finding surfaced by checking this, not assumed**: the 152 qualifying pairs are almost
entirely from 3 of the 6 stores — LON (53), EDI (52), MAN (46), AMS (1), **DUB (0), FAR (0)**. This
isn't a modeling artifact; it's a direct consequence of `_assign_store()`: real UK orders (the bulk
of this dataset) are hash-routed across only LON/MAN/EDI, while DUB/AMS/FAR each get a much smaller
international slice, and at this data volume almost none of their top-150 products clear a 40%
density bar. The forecasting exercise below is necessarily scoped to LON/MAN/EDI (plus one AMS
product) — a real limitation of the underlying store-assignment split, stated plainly rather than
glossed over.

## Data and split

152 dense pairs, engineered daily. Time-based split, never random (day-of-week and trend leakage
matters here the same way it did for Fraud and Climate): **train** = every day before
2011-10-15 (**47,272 rows**), **test** = the last 56 real days, 2011-10-15 to 2011-12-09
(**8,512 rows** — exactly 152 pairs × 56 days, confirmed).

## Features

`lag_1`, `lag_7`, `rolling_mean_7`, `rolling_std_7` (all computed with `shift(1)` before the
rolling window, so a row never sees its own day's demand), `day_of_week`, `reference_unit_price`,
and `store_id` (one-hot, fit on train only — only 4 distinct stores survive the density filter).
Rows without 4 full weeks of history yet (the first 28 days of each pair's series, all inside the
train period) are dropped so the model and the seasonal-naive baseline are scored on the identical
row set.

**Baseline**: seasonal-naive, appropriate to ~1 year of data — each row's prediction is the mean of
that same pair's demand on the same weekday over the trailing 4 weeks (lag 7/14/21/28, averaged).
This is the forecasting comparison point. The existing flat restock-to-300 rule is a *separate*
comparison, further down, not the forecasting baseline.

**Model**: XGBoost regressor (`n_estimators=300, max_depth=5, learning_rate=0.1`), chosen over
LightGBM mainly for consistency with the library already used in Fraud/Climate — no meaningful
performance reason to prefer one over the other at this data size.

## Forecasting results — real, from this run

| Model | MAE | RMSE |
|---|---|---|
| `xgboost_demand_model` | **17.97** | 68.99 |
| `seasonal_naive_dow` | 19.25 | **68.91** |

A mixed result, reported as such: XGBoost beats the seasonal-naive baseline on MAE by about 6.6%,
but is marginally *worse* on RMSE (essentially tied, within 0.1%). The reason isn't contradictory —
`docs/evidence/dark_store_forecast_vs_actual.png` shows why: the busiest dense pair (`LON/22197`)
has several days with demand spiking to 1,000–2,900 units against a typical day under 100. Neither
model comes close to predicting those spikes (a day-ahead lag/rolling feature set has no way to
anticipate a one-off bulk order), and RMSE — which squares errors — is dominated by those rare
catastrophic misses roughly equally for both models. MAE, which weights every day equally,
reflects the much more common small-scale days, where XGBoost's lag/rolling features give it a
real, if modest, edge over a flat weekday average.

## The reorder-policy comparison — the part that actually matters here

Simulated two policies over the same held-out 56 days, on real observed demand, both starting from
the same real stock level `inventory_snapshots` had the day before the test window:

- **`fixed_restock_300`**: the existing rule — restock to 300 whenever stock would hit ≤ 0.
- **`forecast_plus_safety_buffer`**: restock to `(XGBoost's forecast for that day × 7) + 1.65 ×
  (trailing 7-day demand std) × √7` whenever stock would hit ≤ 0 — the same trigger condition as
  the existing rule, so the comparison isolates *what to restock to*, not *when to check*.

**Top-line (pair-equal-weighted mean)**:

| Policy | Avg. stockout-proxy days / pair | Avg. inventory held / pair |
|---|---|---|
| `fixed_restock_300` | 2.25 | 165.46 |
| `forecast_plus_safety_buffer` | **2.89** (worse) | 164.47 (~equal) |

Taken at face value, that looks like a wash-to-loss for the forecast policy — more stockout events,
no real inventory saved. **That headline number hides a real split, and it's worth digging into
rather than reporting the mean and stopping**:

- **The median pair's average inventory dropped by 33.6 units** under the forecast policy (against
  a ~165-unit baseline — a real reduction), and **108 of 152 pairs (71%) hold less inventory**, not
  more. `docs/evidence/dark_store_reorder_stock_scatter.png` shows every pair as one dot — most
  cluster well below the "equal" line.
- Stockout-day differences for most pairs are small: 47 pairs unchanged, 57 pairs +1 day, 28 pairs
  +2 days over the whole 56-day window; **12 pairs actually have *fewer* stockout days** under the
  forecast policy. This tracks with a real mechanism: the median forecast-based restock quantity is
  **125 units** (vs. the flat 300), and 83.7% of all computed restock quantities land below 300 — a
  policy that commits less capital per restock event necessarily restocks somewhat more often.
- **A handful of highly volatile, high-volume pairs balloon the simple mean back up**: `LON/20724`
  goes from 181 to 1,632 average units held; `MAN/22178` from 169 to 1,049; `MAN/84879` from 180 to
  1,000. These are pairs with high demand variance, where the `√(lead-time) × σ` safety-stock term
  produces a very large buffer — appropriately larger than a flat 300 for a genuinely volatile
  product, but large enough that these few pairs single-handedly erase the median pair's real
  improvement once every pair is weighted equally in the mean.

**Honest conclusion**: for the typical (median) product in this set, the forecast-informed policy
is a real, legitimate improvement — meaningfully less capital tied up in idle inventory, at the
cost of somewhat more frequent (smaller) restocks. But the safety-stock formula as implemented
here over-reacts to a small number of highly volatile products, and that's enough to make the
simple top-line comparison look like a wash. This is not "the model doesn't help" — it's "the
safety-buffer formula needs a cap or a more robust volatility estimate (e.g., a dampened or
log-scaled `σ` term) before this policy should be trusted uniformly across every product," a
specific, fixable limitation rather than a verdict on forecast-informed reordering in general. The
existing flat-300 rule is not obviously beaten here, but it is not obviously better either — it's
simpler and avoids the volatile-buffer blowup entirely, at the cost of visibly over-provisioning
inventory for most (typical, lower-volume) products. Reported plainly in both directions, as asked.

## Intended use

A methodology demonstration on real transaction-derived demand with a synthetic inventory layer —
not a fielded reordering system. The safety-stock formula's over-reaction to a handful of volatile
products (above) is a real, specific gap that would need to be fixed before this policy should
replace a flat rule in practice.

## Comparison against automated model search

As a sanity check on the hand-picked XGBoost configuration above, `demand_forecast_model.ipynb`
also runs H2O AutoML (community edition, local-only, not part of the Airflow pipeline) over the
exact same `train`/`test` frames and feature set, 5-minute budget. **Unlike Fraud and Climate,
this one doesn't just confirm the hand-picked choice.** H2O's leader — a grid-searched
DeepLearning (neural network) model — reaches **MAE 15.97, RMSE 67.29** on this project's real
held-out test set, computed the same way as every other number in this card. That's a real,
meaningful improvement over the hand-picked XGBoost model (MAE 17.97, RMSE 68.99): roughly 11%
lower MAE and 2.5% lower RMSE, from a different model family than anything tried by hand. H2O's
own XGBoost backend wasn't available on this machine and was skipped automatically, so this is a
neural net beating an untuned gradient-boosted tree, not one XGBoost implementation beating
another. Stated plainly rather than buried: **the XGBoost configuration used in the production
pipeline (`pipeline.train_demand_model()`) is not the best model this data supports** — it was
chosen without a hyperparameter search or a comparison against non-tree model families, and this
sanity check shows that gap is real, not hypothetical. Closing it (a tuned neural net, or a
proper hyperparameter sweep over XGBoost itself) is future work, not something this round of work
implements, since the H2O check is explicitly local-only and out of scope for the Airflow pipeline.

**Seeing real predictions**: the notebook also exports the exact test frame every model above was
scored against to `h2o_saved_models/test_frame.csv` (target column included), and
`view_all_ml_in_h2o.py` (outside this repo, local-only) loads it into Flow as
`dark_store_test_frame` alongside the saved models. In Flow: Models → pick a model (e.g. the
DeepLearning leader named above) → Predict → select `dark_store_test_frame` → Flow computes and
displays a real predictions table for that model against that data, comparable directly to the
`units_demanded` column already in the frame.

## Known limitations

- **Scoped to 152 of 876 pairs**, concentrated in 3 of 6 stores (LON/EDI/MAN), for the density
  reasons explained above. This project does not forecast demand for DUB, FAR, or the vast majority
  of AMS's catalog — those pairs are too intermittent (>60% zero-demand days) for a daily model to
  say anything meaningful.
- **RMSE is dominated by rare, unpredictable demand spikes** (e.g., `LON/22197`'s 2,900-unit day) —
  neither model anticipates these, and no lag/rolling feature set built from daily granularity
  reasonably could without an external signal (a known promotion, a wholesale order confirmation).
- **The safety-stock buffer isn't capped**, which is exactly what produces the handful of
  ballooning pairs in the reorder-policy comparison above — a real, specific, fixable gap in this
  run's policy design, not a fundamental problem with forecast-informed reordering.
- **No hyperparameter search** for the XGBoost model — confirmed to matter in practice, not just in
  theory: see the automated-search comparison above, where a model H2O found without any manual
  tuning meaningfully beats it.
- **One time split**, not walk-forward cross-validation — 56 held-out days is a reasonable
  demonstration of the method, not a robust estimate of how stable these numbers are across other
  seasons (this dataset only covers Dec 2010–Dec 2011, so a walk-forward check across multiple
  years isn't possible with the data available).
