I've added the Databricks job definition, but I haven't deployed it or run it. I only checked that the JSON is valid.

**Files added**
- `databricks/dbt_daily_job.json`: the job definition for the Jobs API (`POST /api/2.2/jobs/create`).
- `databricks/profiles.yml`: a Snowflake connection profile for `shop_analytics` that reads every connection setting from environment variables. The job needs this file, and the repo didn't have one.

**What the job does**
- **Schedule:** runs every day at 05:00 (`0 0 5 * * ?`). Only one run is allowed at a time, and it times out after 2 hours.
- **Job cluster:** a single-node cluster (`m5d.large`, DBR 16.4 LTS). That size is enough because the queries run in Snowflake, not on the cluster.
- **Task:** a `dbt_task` that checks out the repo from Git and runs `dbt deps` then `dbt build --target prod`. It installs `dbt-snowflake` from PyPI.
- **Credentials:** the cluster loads them from a Databricks secret scope called `dbt_snowflake` and passes them to dbt as environment variables.
- **Failures:** the job retries once after 10 minutes and sends a failure email.

**Before you create the job**
1. **Timezone:** I set `timezone_id` to `UTC`. If you meant 5am local time, change it (for example to `America/New_York`).
2. **Repo URL:** replace `git_url`. This repo has no remote configured, so I couldn't fill it in.
3. **Alert email:** replace the placeholder in `email_notifications`.
4. **Secrets:** create the scope and add the keys `account`, `user`, `password`, `role`, `warehouse` and `database`:
   ```
   databricks secrets create-scope dbt_snowflake
   databricks secrets put-secret dbt_snowflake password
   ```
   For production, consider key-pair authentication instead of a password.
5. **Cloud:** `m5d.large` is an AWS instance type. On Azure use something like `Standard_D4ds_v5`; on GCP, `n2-standard-4`.

Then create the job with:
```
databricks jobs create --json @databricks/dbt_daily_job.json
```