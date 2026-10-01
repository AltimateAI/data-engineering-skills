I fixed `partner_feed`, and it now runs end to end on Airflow 3.3.2 whether the run has a logical date or not. The only file changed is `dags/partner_feed.py`, and nothing is committed yet.

## Why it broke
- **Nightly run:** Airflow 3 removed `execution_date` from the task context, so `write_manifest` failed with `KeyError: 'execution_date'`. `extract_orders` was fine because it already used `logical_date`.
- **UI trigger with no date:** in Airflow 3 that run has no logical date at all. Airflow then leaves `logical_date`, `ds`, `ds_nodash`, etc. out of the context entirely. So `extract_orders` failed first, and `deliver`'s `{{ ds_nodash }}` would have failed after it.

## The fix
I added one helper, `feed_day(dag_run)`, which picks the day the run produces the feed for:
- If the run has a logical date, it uses it, so scheduled runs and dated triggers behave as before.
- If not, it uses the run's `run_after`, which for a date-less manual trigger is the trigger time (in UTC). Clearing a run doesn't change this value (I checked the Airflow source and tested it), so a re-run tomorrow still produces the original day's feed.

All three steps now use the helper. `deliver` calls it from its template, giving the same `acme_orders_YYYYMMDD.csv` / `.manifest.json` names. The task order, output paths and outbox names are unchanged.

## How I tested it
I ran the DAG locally with Airflow's test runner against a temporary database:

| Run | Original code | Fixed code |
|---|---|---|
| With logical date 2026-03-02 | failed: `KeyError: 'execution_date'` in `write_manifest` | succeeded: 4 ACME rows, `acme_orders_20260302.*` |
| No logical date | failed: `KeyError: 'logical_date'` in `extract_orders` | succeeded: `acme_orders_20261001.*`, manifest partition `2026-10-01` |
| Clear the no-date run | — | the date the feed is based on (`run_after`) stayed the same |

Both failures matched yours exactly before the fix. I deleted all test output afterwards, including an `airflow.cfg` my first attempt had accidentally written into the repo.

The test data only has March orders, so today's (2026-10-01) feed has 0 rows. That's correct, not a bug. Also, "the day it was triggered" is the UTC day, so a trigger at 01:00 UTC produces that UTC date even if it's still the previous evening locally.