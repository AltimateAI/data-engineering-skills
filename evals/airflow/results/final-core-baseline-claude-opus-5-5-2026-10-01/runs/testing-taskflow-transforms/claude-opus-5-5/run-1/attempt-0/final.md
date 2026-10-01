I've written a pytest suite under `tests/`: 28 tests, and `pytest tests/` passes on the current code in about 4 seconds. The DAG is unchanged and nothing is written to the repo's `output/`. I haven't committed anything.

**Files**
- `tests/conftest.py` points Airflow at a throwaway home directory and SQLite database before anything imports it, so CI's real Airflow home isn't touched. The end-to-end tests need that database, but no scheduler or webserver. Tests write output to a pytest temp directory.
- `tests/test_transforms.py` calls each task function directly:
  - **Duplicates:** the latest version is kept whether it appears first or last in the export, and all of its fields win.
  - **Rounding:** genuine half-cent cases like 0.025 → 0.03 and 0.125 → 0.13, where banker's rounding would differ, and 1.005 → 1.01, which float maths gets wrong.
  - **FX rates:** only the run day's rates are used. An order whose currency has a rate on another day but not that day fails.
  - **Validation:** a missing customer or a negative amount is rejected.
- `tests/test_dag.py` covers the DAG itself:
  - **Publishing:** `load_enriched` only runs after `validate_totals` succeeds.
  - **Schedule:** checked with Airflow's own scheduling logic; the next four runs are 06:00 UTC on consecutive days.
  - **End-to-end runs:**
    - The sample data for 2026-03-02 produces exactly the expected file, including both re-exported orders.
    - A missing FX rate fails the run and writes nothing.
    - A failed validation also writes nothing.

**Checking the tests catch real bugs:** I put the bugs below into the DAG one at a time and ran the suite each time. Every one made tests fail, and I restored the file from git after each run.
- keeping the oldest or the last-seen version of a duplicate
- banker's rounding
- float maths
- falling back to a rate of 1 when one is missing
- using another day's rate
- publishing without validation
- changing the schedule to 07:00

**Things to know**
- **Retries are off in the end-to-end tests.** The DAG retries failures after 10 minutes, and Airflow's test runner really waits for that, so the failure tests turn retries off on their own copy of the DAG.
- **Two schedule assumptions depend on Airflow config, not the DAG file.** Neither is set explicitly in the DAG:
  - It reads 06:00 as UTC only because Airflow's default timezone is UTC.
  - "The 06:00 run on day D processes day D's orders" holds only while `create_cron_data_intervals` stays off, which is the Airflow 3 default. Airflow's unit-test mode turns it on; I hit this while writing the tests and kept that mode out of the setup. If production turns it on, each run would process the previous day.

  It's worth confirming both in production config.
- **These tests don't explain last month's wrong number.** The current code does everything finance listed correctly on the sample data. One fragile spot I noticed: duplicates are ranked by comparing `updated_at` as text. That's only correct while every export uses the identical timestamp format; a mix like `T9:05` vs `T09:05`, or added timezone offsets, would pick the wrong version without any error. I didn't add a test for that because finance's rules don't specify a format.