I wrote the job definition to `databricks/dbt_build_job.json`. It parses as valid JSON, but I haven't submitted it to Databricks.

- **Schedule:** `0 0 5 * * ?` runs daily at 5:00 AM, with the timezone set to `UTC`. Change `timezone_id` if you mean local time.
- **Cluster:** a job cluster (`dbt_cluster`) that exists only for each run, with 1 worker, runtime 15.4 and `i3.xlarge`. `i3.xlarge` is an AWS node type, so swap it on Azure or GCP.
- **Task:** a `dbt_task` that runs `dbt deps` and then `dbt build`. It installs `dbt-databricks` as a library and pulls the project from `git_source`.
- **Run settings:** one concurrent run, a 2-hour timeout and one retry.

Fill in or check these before using it:
1. **Git URL:** `git_source.git_url` is a placeholder, because the repo has no remote configured.
2. **Catalog and schema:** `catalog` and `schema` are placeholders for where the models should be built.
3. **Warehouse mismatch:** the README says this project is on Snowflake, and `sources.yml` reads from a `raw` schema. This job targets Databricks, so the `raw` data has to exist in your Databricks catalog.
4. **Profile name:** `dbt_project.yml` uses `profile: shop_analytics`, and there is no `profiles.yml`. If the profile that Databricks generates doesn't match that name, add a `profiles.yml` for the Databricks target to the repo. Then set `profiles_directory` in the `dbt_task`.

To deploy it, run `databricks jobs create --json @databricks/dbt_build_job.json`.