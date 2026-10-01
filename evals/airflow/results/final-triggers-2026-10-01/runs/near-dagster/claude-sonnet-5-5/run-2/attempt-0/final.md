I rewrote `flows/etl.py` as a Dagster job, but I haven't run it or installed Dagster, so it's untested.

- **Ops and job:** `extract`, `transform` and `load` are now `@op`s. `etl_job` chains them in the same order. `load` logs through `context.log` instead of `print`.
- **Schedule:** `etl_daily_schedule` uses the cron `0 4 * * *` with `execution_timezone="UTC"`, so it runs daily at 04:00 UTC.
- **Registration:** a `Definitions` object registers the job and schedule, so `dagster dev -f flows/etl.py` should pick them up.
- **Direct run:** `python flows/etl.py` still works and now runs the job with `execute_in_process()`.

I also added `dagster` to `dependencies` in `pyproject.toml`, which the project didn't list before. Nothing else in the repo references `etl`.