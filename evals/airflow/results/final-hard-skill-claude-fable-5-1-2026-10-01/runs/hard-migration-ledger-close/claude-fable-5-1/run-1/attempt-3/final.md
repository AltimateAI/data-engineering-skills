Migration complete and verified. Every scheduled run and the runbook's manual re-close produce byte-identical output on Airflow 3.3.2 and on Airflow 2.11.2, audit records included.

**What changed (source 2.11.2, target 3.3.2)**

- **Every bare schedule became an explicit interval timetable.** On Airflow 3 a bare cron, preset or `timedelta` is a trigger timetable, so `ds` would have become the day the run fires and every output would have shifted one period. The weekly report, FX revaluation, hourly extract and New York payments now use `CronDataIntervalTimetable` and housekeeping uses `DeltaDataIntervalTimetable`. Existing explicit `catchup` values were kept.
- **daily_close manual re-close.** Airflow 3's plain `airflow dags trigger` carries no logical date or data interval, so the template would have failed. A new `close_interval` helper in the workdays module returns the run's interval for scheduled runs, and for manual runs rebuilds the latest ended weekday from the trigger time, exactly what Airflow 2 inferred. The SQL template, the target path and `roll_balances` all read it.
- **Audit record.** Airflow 3 dropped `DagRun.external_trigger`. The operator now marks a run "operator" when its run type is manual, "scheduler" otherwise. The operator base moved to `airflow.sdk`.
- **Removed context keys.** The weekly report's `prev_ds` parameter is computed as the previous Monday. In the FX SQL, `next_ds` became the interval end's date and `yesterday_ds` became `ds` minus one day. `conf` is injected via `user_defined_macros`.
- **Hourly cursor.** The cross-run `xcom_pull` gained `map_indexes=-1`. Without it, Airflow 3 returns a list of all earlier cursors from the third run on.
- **Imports, requirements, README.** All imports moved to `airflow.sdk` and `airflow.providers.standard`. `requirements.txt` pins Airflow 3.3.2 and the standard provider. The README explains the timetable choice and the manual re-close behaviour. The business-day timetable and the `macros.ledger.*` plugin are unchanged and still work on 3.3.

**Verified**

- Checker: 0 import errors, 0 errors. Ruff AIR rules: clean on dags and plugins.
- Run preview: all six DAGs' next five fire times, logical dates and intervals match a preview taken with the real 2.11.2 interpreter.
- Replay against one metadata DB per side, 2.11.2 versus 3.3.2: 31 runs, including 8 consecutive hourly extracts, the DST weekend for the New York payments, and two manual `daily_close` triggers (mid-week and Monday morning, which re-closed the previous Friday). All 45 output files are identical, and the two re-closed days carry `"started_by": "operator"`. The manual runs on 3.3 ran with no logical date, the way production triggers will.

**Not verified or left out**

- Manual triggers of the other five DAGs are not in the runbook and were not ported. On 3.3 such a trigger fails with an undefined-date error rather than writing a shifted file.
- The project has no test suite, so none was run. Nothing is committed. The replay copies live under the temp directory `mig` if you want to inspect them.