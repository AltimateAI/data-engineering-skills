Both marketing DAGs now run on Airflow 3.3.2. Each weekly run still summarises the right week, a season re-run still produces one run per week, and the on-call page still fires at Monday 09:00 UTC. Nothing is committed yet.

**What changed and why**

- **Both DAGs:** switched to the 3.x imports and replaced `schedule_interval` with `schedule`. `requirements.txt` is bumped to 3.3.2.
- **Season re-runs:** Airflow 3 turns catch-up off by default, which would have silently stopped the one-run-per-week behaviour. I set `catchup=True` explicitly. From the Jan 5 start date it schedules 38 weekly runs, from Jan 5–12 through Sep 21–28.
- **Which week a run covers:** under 3.x's default schedule handling, the Monday run would have reported on the wrong week, and the `next_ds` value the task used no longer exists. I kept the old weekly-interval behaviour and the task now reads the week's start and end directly. A test run for Monday Jan 5 wrote `2025-12-29.csv` with the same totals as before, so it still covers the previous Mon–Sun week.
- **On-call page:** SLAs no longer exist in Airflow 3. Their replacement, a "deadline alert", is set for Monday 09:00 UTC, the same time the SLA fired. I confirmed this through the real scheduler path, and the deadline is cleared if the report finishes in time.

**Things to check before deploying**

1. **The paging function moved to a new file, `plugins/marketing_alerts.py`.** In 3.3 the page is sent by Airflow's triggerer service, which can't load code from the DAGs folder. Platform needs the triggerer running with this `plugins/` folder deployed to it, or nobody gets paged. I noted this in the README.
2. **Re-running a season no longer pages for past weeks.** In 3.3 every historical week in a re-run would be past its deadline, so on-call would get one page per week, 38 for the current season. The callback now skips runs created a week or more after their Monday deadline. A late current Monday report still pages; I tested both cases through Airflow's own trigger runner. If growth actually wants those historical pages, it's a one-line removal.
3. **`airflow dags test` ends with an error for the weekly DAG.** Both tasks succeed and write their files, then it fails with `'dict' object has no attribute 'hex'`. The same completion step works in the scheduler code path, so I believe this is an Airflow 3.3.2 bug in the test command for DAGs with deadline alerts, not a problem in the port.

`notify_growth_oncall` still only prints a message, as it did before. Wiring it to your real paging tool is out of scope here.