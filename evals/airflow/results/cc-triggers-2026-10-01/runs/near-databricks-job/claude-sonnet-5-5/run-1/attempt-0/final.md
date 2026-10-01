I wrote the job definition to `databricks/dbt_build_job.json`. It's valid JSON, but I haven't submitted it to Databricks.

- **Schedule:** it runs at 05:00 every day (`0 0 5 * * ?`) in UTC. Change `timezone_id` if you mean 5am in another timezone.
- **Compute:** a job cluster called `dbt_cluster` (1 worker, Databricks Runtime 15.4, `i3.xlarge`). It is created for each run and shut down afterwards.
- **Task:** a single `dbt_task` that runs `dbt build`, with `dbt-databricks` installed on the cluster. The job allows one concurrent run, retries once on failure and times out after 2 hours.
- **Source:** the project is pulled from Git (`main` branch, root directory).

Before you use it, change these:
1. **`git_url`:** I used a placeholder, so set it to your repo.
2. **Warehouse mismatch:** your README says this project runs on Snowflake, and the repo has no `profiles.yml`. I assumed the job should target Databricks. If dbt should still write to Snowflake, swap the library to `dbt-snowflake`.
3. **`profiles_directory`:** point it at a real workspace folder holding a `profiles.yml` for `shop_analytics`. The `analytics` schema is a placeholder too.
4. **Cluster and alerts:** adjust `node_type_id` for your cloud (`i3.xlarge` is AWS) and replace the failure-alert email.

To create the job, run `databricks jobs create --json @databricks/dbt_build_job.json`.