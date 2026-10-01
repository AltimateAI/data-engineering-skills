I added a pytest suite under `tests/` with 26 tests, and it passes on the current DAG (`pytest tests/`, about 1.6s). It needs no scheduler, webserver or database, and `dags/orders_enrichment.py` is unchanged.

**What it covers**
- **Latest version wins:** the latest `updated_at` is kept whatever the row order. Distinct orders come out sorted by id, and empty input is handled.
- **Rounding:** `amount_usd` is checked half-up with exact ties. For example, 1.00 × 0.125 gives 0.13, where banker's rounding would give 0.12. Other cases check rounding down, the sample S-105 (0.35 × 1.0850 = 0.38), and USD passing through at rate 1.
- **Missing rate:** an order in a currency with no rate for the day raises an error naming the currency and the order. A rate from a different day isn't used.
- **Validation and writing:** `validate_totals` rejects a blank customer or a negative USD amount. `load_enriched` writes only the five output columns.
- **Schedule:** the cron expression is `0 6 * * *` in UTC.
- **Wiring:** `load_enriched` has `validate_totals` as its only upstream task, and `validate_totals` follows `convert_to_usd`.
- **End to end:** the sample data for 2026-03-02 produces S-102 (120.00 → 130.20), S-103 (40.50 → 51.44), S-104 and S-105. The superseded versions are gone.
- **Failed runs:** end-to-end runs with an injected JPY order, and with a blank customer, both fail and leave no `output/` directory.

I temporarily broke the DAG three ways: banker's rounding, taking the oldest version instead of the latest, and defaulting a missing rate. Each time the suite failed. I then restored the DAG from git, which is clean.

**Limits**
- The end-to-end test calls the task functions in the DAG's order against a temp copy of `data/`. It doesn't run Airflow's executor, because that needs a metadata DB, which your CI setup doesn't have. A separate structural test checks that the real DAG is wired the same way. Together they would miss a bug that only appears when Airflow runs the tasks.
- "Nothing written unless validate_totals passed" is tested both ways: the wiring, and an end-to-end run that fails validation and writes nothing. Airflow itself enforces that downstream tasks skip when an upstream task fails.
- If two versions of an order have identical `updated_at`, the first one in the file wins. Your rules don't say which should win, so I didn't pin that down in a test.

The files are `tests/conftest.py` and `tests/test_orders_enrichment.py`. I haven't committed anything.