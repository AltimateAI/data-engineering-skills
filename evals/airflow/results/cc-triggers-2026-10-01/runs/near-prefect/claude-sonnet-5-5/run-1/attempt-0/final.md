`flows/etl.py` is now a Prefect flow, but I haven't run it or installed Prefect, so it's untested.

- **Tasks:** `extract`, `transform` and `load` are each a `@task(retries=3)`.
- **Flow:** an `etl` flow calls them in order.
- **Schedule:** `python flows/etl.py` runs `etl.serve(name="etl-hourly", cron="0 * * * *")`. That registers a deployment that runs at the top of every hour. The process has to stay running to execute the runs.
- **Dependency:** I added `dependencies = ["prefect>=3"]` to `pyproject.toml`.

If you'd rather have a work pool and worker than a long-running `serve` process, or a `prefect.yaml`, I can switch it.