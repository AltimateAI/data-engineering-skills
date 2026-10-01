I wrote the job definition to `databricks_job.json`. It parses as valid JSON, but I haven't submitted it to Databricks.

One thing to check first: the README says this project is on Snowflake, and there's no `profiles.yml`. I wrote the job for Databricks, as you asked. The `dbt_task` has Databricks generate the connection profile for the job cluster. If you're moving the project to Databricks, the models may need dialect changes.

What the job does:
- **Schedule:** runs daily at 5:00 AM, with `quartz_cron_expression` set to `0 0 5 * * ?`. Only one run can be active at a time.
- **Cluster:** a job cluster named `dbt_cluster`, with 1 worker on Databricks Runtime 15.4 and single-user access mode. It's created for each run and terminated afterwards.
- **Task:** `dbt build` through a `dbt_task`, with `dbt-databricks` installed as a library. It writes to catalog `main`, schema `shop_analytics`. It retries once after 5 minutes and has a 2-hour timeout.
- **Source:** the dbt project is pulled from Git.

Placeholders to change:
- **`git_source.git_url`:** set this to your real repo. The repo has no remote configured, so I couldn't fill it in.
- **`timezone_id`:** I used `UTC`. Set it to your zone, such as `America/Los_Angeles`, if 5am should be local time.
- **`node_type_id`:** `i3.xlarge` is an AWS node type. On Azure or GCP, use that cloud's equivalent.
- **`catalog` and `schema`:** change these to your target names.
- **`email_notifications.on_failure`:** it's an empty list, so add addresses to get alerts.

To create it, run `databricks jobs create --json @databricks_job.json`.