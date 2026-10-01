I rewrote `flows/etl.py` as a Dagster job with a daily schedule at 04:00 UTC. I haven't run it or imported Dagster, so it's untested.

- **Ops:** `extract`, `transform` and `load` are now `@op`s. `load` logs through `context.log.info` instead of `print`.
- **Job:** `etl_job` wires them together as extract → transform → load.
- **Schedule:** `etl_daily_schedule` runs `etl_job` with cron `0 4 * * *` and `execution_timezone="UTC"`.
- **Definitions:** `defs` bundles the job and schedule so Dagster can load the file, for example with `dagster dev -f flows/etl.py`.

I removed the `if __name__ == "__main__"` runner. To run it once by hand, use `etl_job.execute_in_process()` or the Dagster UI.

I also added `dependencies = ["dagster"]` to `pyproject.toml`, since the project didn't declare it. I didn't pin a version.

For the schedule to fire, a Dagster daemon has to be running, which `dagster dev` starts for you.