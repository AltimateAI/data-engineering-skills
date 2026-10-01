I converted `flows/etl.py` into a Prefect flow, but I haven't run it or installed Prefect, so it's untested.

- **Tasks:** `extract`, `transform` and `load` are each a `@task(retries=3)`.
- **Flow:** a new `etl` flow runs them in order: `load(transform(extract()))`.
- **Schedule:** running `python flows/etl.py` now calls `etl.serve(name="etl-hourly", cron="0 * * * *")`. That starts a long-running process that runs the flow at the top of every hour.
- **Dependency:** I added `dependencies = ["prefect>=3"]` to `pyproject.toml`.

`serve()` only schedules runs while that process stays up. Run it under something like systemd, Docker or a similar supervisor. If you'd rather have a work-pool deployment with a `prefect.yaml` and a worker, say so and I'll switch it.