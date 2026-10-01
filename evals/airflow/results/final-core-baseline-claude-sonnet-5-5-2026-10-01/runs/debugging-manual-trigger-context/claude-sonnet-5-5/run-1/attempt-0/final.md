I fixed `dags/partner_feed.py`, but I haven't run the DAG end to end. The sandbox wouldn't let me create an Airflow home, so I couldn't try `dag.test()`. I checked the new date helper directly with fake run objects: a run with no logical date gave the `run_after` day, and a run with a logical date gave that date.

**Causes**
- **`write_manifest` (scheduled runs):** it read `context["execution_date"]`. Airflow 3 removed that key, so every run failed there.
- **`extract_orders` (manual trigger with no date):** in Airflow 3 a run triggered without a logical date has `logical_date` set to `None`. The task runner then leaves `logical_date`, `ds` and `ds_nodash` out of the context entirely, which gives your `KeyError: 'logical_date'`.
- **`deliver` (not reported yet):** it uses `{{ ds_nodash }}` in its template, so it would have failed the same way on a dateless manual run once `extract_orders` was fixed.

**Fix**
- I added a `feed_day(dag_run)` helper. It uses the run's logical date when there is one, and otherwise the run's `run_after`, converted to UTC. `run_after` is set when the run is created and doesn't change on clear, so re-running a manual run tomorrow still produces the day it was triggered.
- `extract_orders` and `write_manifest` both call that helper, so they always agree on the day.
- `deliver` gets the helper through `user_defined_macros` and uses `{{ feed_day(dag_run).replace('-', '') }}` in place of `ds_nodash`.
- Output paths, outbox file names and the extract → manifest → deliver chain are unchanged.

The date for scheduled runs and runs triggered with a date is unchanged: it's still the logical date. The one change is that I now convert it to UTC explicitly. That only matters if a logical date is ever in another timezone.

Before you rely on it for ACME, trigger it once from the UI with the date empty. Then clear that run and confirm it still writes the original day's files.