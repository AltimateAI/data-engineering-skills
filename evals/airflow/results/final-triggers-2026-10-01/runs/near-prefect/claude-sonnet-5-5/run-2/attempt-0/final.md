I rewrote `flows/etl.py` as a Prefect flow, but I haven't run it or installed Prefect, so it's untested.

- **Tasks:** `extract`, `transform` and `load` are each a `@task(retries=3)`.
- **Flow:** a new `etl` flow calls them in order, `load(transform(extract()))`.
- **Schedule:** `python flows/etl.py` now calls `etl.serve(name="etl-hourly", cron="0 * * * *")`. That registers a deployment that runs at the top of every hour. The process has to stay running, because `serve` executes the runs itself.
- **Dependency:** I added a `flows = ["prefect>=3"]` extra to `pyproject.toml`. Install it with `pip install -e ".[flows]"`.

If you'd rather have a `prefect.yaml` deployment that runs on a work pool and worker, I can switch to that.