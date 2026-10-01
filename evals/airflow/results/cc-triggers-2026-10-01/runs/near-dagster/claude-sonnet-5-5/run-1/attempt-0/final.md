I rewrote `flows/etl.py` as a Dagster job with a daily schedule at 04:00 UTC. I haven't run it or imported it, and `dagster` isn't verified as installed here.

- **Ops:** `extract`, `transform` and `load` are now `@op`s with the same logic as before. `load` logs through `context.log.info` instead of `print`.
- **Job:** `etl_job` wires them together as extract → transform → load.
- **Schedule:** `etl_daily_schedule` uses the cron `0 4 * * *` with `execution_timezone="UTC"`.
- **Definitions:** `defs = Definitions(jobs=[etl_job], schedules=[etl_daily_schedule])` is there so Dagster can discover everything.
- **Dependency:** I added `dependencies = ["dagster"]` to `pyproject.toml`, since the project didn't list it.

I removed the `if __name__ == "__main__"` block. To run it locally, use `dagster dev -f flows/etl.py`. The schedule only fires when the Dagster daemon is running.