I added the suite under `tests/` (`conftest.py` and `test_orders_enrichment.py`). `pytest tests/` gives 23 passed in about 1.5s, and the DAG is unchanged. I didn't run a check that deliberately breaks the DAG, so I haven't seen the tests fail on a bug.

**What each rule has**
- **Dedupe:** the latest `updated_at` wins whatever the row order, and distinct orders come out sorted by `order_id`.
- **Rounding:** seven cases, including exact half-cent ties (`1.00 × 0.125 → 0.13`, `2.00 × 0.1225 → 0.25`) where banker's rounding would give a different answer. There's also a just-below-tie case and the real `40.50 GBP → 51.44`.
- **Missing FX rate:** `convert_to_usd` raises `ValueError` naming the currency and order. `load_fx_rates` returns only the run date's rates (USD is implicit) and never falls back to another day.
- **No write before validation:** the DAG test asserts `load_enriched` depends only on `validate_totals`, which depends on `convert_to_usd`. Two end-to-end runs, one with a missing rate and one with a blank `customer_id`, confirm nothing is written to the output directory.
- **Schedule:** the cron expression is `0 6 * * *`, the timezone is UTC, and `catchup` is False.
- **End-to-end:** the sample `data/` for 2026-03-02 gives the exact output CSV, with S-102 deduped to 120.00 → 130.20 and S-105 as 0.35 → 0.38.

**How the end-to-end test runs**
- There's no scheduler or DB here, so the test calls each task's underlying function in DAG order (`.function`). It points `DATA_DIR` and `OUTPUT_DIR` at temp paths, and the real `output/` is never touched.
- The order of those calls is copied from the DAG by hand. The structure test checks the real DAG's dependencies, but nothing checks that the helper's call order matches them.
- This doesn't exercise Airflow's own task execution or XCom passing. I tried `dag.test()` but couldn't set up an Airflow DB in this sandbox, so I haven't checked whether it would work in CI.

**Things the tests don't cover**
- Dedupe uses string comparison on `updated_at`. That's correct for ISO timestamps, but a different format would silently pick the wrong version.
- On an exact `updated_at` tie, the first row wins. I left that untested because it isn't one of your rules.
- `validate_totals` checks only for a blank customer and a negative USD amount.

I haven't committed anything.