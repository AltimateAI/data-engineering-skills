I added a pytest suite under `tests/` and left the DAG untouched. `pytest tests/ -q` gives 27 passed in about 8 seconds on Airflow 3.3.2 (the version pinned in `requirements.txt`). It uses a throwaway sqlite DB, so no scheduler or webserver is needed. `git status` shows only the new `tests/` directory.

| What finance relies on | Test |
|---|---|
| Latest version by `updated_at` wins | `test_dedupe_*`, three cases covering row order, many versions and distinct orders. The end-to-end test also checks S-102 and S-103 from the sample data. |
| `amount_usd` = amount × that day's rate, half-up to cents | `test_amount_usd_is_rounded_half_up` (9 cases), `test_each_order_uses_its_own_currency_rate`, `test_fx_rates_are_the_run_dates_rates` |
| Currency with no rate fails the run | `test_missing_fx_rate_fails_instead_of_guessing` (unit) and `test_missing_fx_rate_fails_the_run_and_writes_nothing` (full DAG run) |
| Nothing in `output/` unless `validate_totals` passed | `test_nothing_is_written_before_validate_totals` (task order), `test_failed_validation_publishes_nothing` (full runs with a missing customer and a negative amount), plus the `validate_totals` unit tests |
| Daily at 06:00 UTC | `test_runs_daily_at_0600_utc` checks 10 upcoming runs for hour, minute, UTC offset and exactly one day apart |
| End to end on `data/` | `test_sample_data_end_to_end` runs 2026-03-02 and expects S-102, S-103, S-104 and S-105 with USD of 130.20, 51.44, 9.99 and 0.38. I worked these out by hand. S-103 is an exact half-cent tie (51.435). |

I also planted 15 bugs in the DAG, one at a time, and the suite caught all 15. They covered the dedupe comparison, rounding mode, a default FX rate, bypassing validation, a weaker validation rule, the date filters and a changed schedule.

- **Retries:** the DAG retries failed tasks twice, 10 minutes apart, and `dag.test()` honours that. My first run hung on the failure-path tests. The end-to-end fixture now sets `retry_delay` to zero on the parsed tasks and keeps the retries.
- **Output location:** the end-to-end tests write to `tmp_path`, not the repo's `output/`.
- **Tests that replace data:** they swap `DATA_DIR` for crafted CSVs in `tmp_path`, so they don't touch the sample data.
- **Manual runs (not tested):** `ds` is undefined for manually triggered runs on Airflow 3, so a manual trigger may behave differently from a scheduled run. The README's `airflow dags test … 2026-03-02` form passes a date explicitly. The suite only covers scheduled-style runs and doesn't test manual triggers.
- **Not verified:** the scheduler itself, since the suite checks the timetable's next runs rather than a live scheduler. I also only ran against Airflow 3.3.2.

I didn't commit anything.