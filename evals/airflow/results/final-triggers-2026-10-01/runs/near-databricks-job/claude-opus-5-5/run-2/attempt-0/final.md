I added the job definition at `databricks/dbt_daily_build.json`, plus a `databricks/profiles/profiles.yml` it depends on. Both files parse as valid JSON/YAML, but I haven't submitted the job to Databricks or run dbt, so it's untested. To create the job:

```bash
databricks jobs create --json @databricks/dbt_daily_build.json
```

**What the job does**
- **Schedule:** every day at 05:00 (`0 0 5 * * ?`). The time zone is set to **UTC** because I don't know yours; change `timezone_id` (e.g. `America/New_York`) if you meant local time.
- **Cluster:** a new single-node job cluster for each run (16.4 LTS runtime, `i3.xlarge`). That node type only exists on AWS; on Azure or GCP, swap in something like `Standard_DS3_v2` or `n2-standard-4`.
- **Task:** a dbt task that runs `dbt deps` then `dbt build --target prod`, with code pulled from Git on `main`. `dbt deps` does nothing yet because there's no `packages.yml`, but it's ready if you add packages later.
- **Safety settings:** only one run at a time, a 2-hour timeout, 1 retry after 10 minutes, and an email on failure.

**Your warehouse is Snowflake, not Databricks.** The README says the project runs on Snowflake, so Databricks can't generate the dbt connection settings for you. The job installs the Snowflake adapter (`dbt-snowflake`) and uses the new `profiles.yml`, which reads credentials from environment variables. The job fills those from a Databricks secret scope called `dbt`. You'll need to create it:

```bash
databricks secrets create-scope dbt
databricks secrets put-secret dbt snowflake_account   # repeat for: snowflake_user, snowflake_password,
                                                      # snowflake_role, snowflake_warehouse,
                                                      # snowflake_database, snowflake_schema
```

**Placeholders to fill in**
- `git_source.git_url`: the repo has no Git remote, so I couldn't fill this in. Private repos also need a Git credential set up in Databricks.
- `email_notifications.on_failure`: the address to alert.

**The first run will fail as the project stands:** `models/marts/orders.sql` references `ref('stg_customers')`, but that model doesn't exist. Only `stg_orders.sql` is in `models/staging/`, so `dbt build` will stop with a compilation error until you add it.