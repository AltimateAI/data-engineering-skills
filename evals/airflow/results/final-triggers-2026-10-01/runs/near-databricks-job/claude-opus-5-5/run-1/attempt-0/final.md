I added two files: the job definition at `databricks/dbt_daily_job.json` and a `databricks/profiles.yml` for it to use. The JSON parses cleanly, but I haven't submitted the job to Databricks or run dbt.

**What the job does**
- **Schedule:** runs daily at 05:00 (`0 0 5 * * ?`). The timezone is **UTC** — change `timezone_id` if you meant something else, for example `America/New_York`.
- **Cluster:** a new single-node job cluster (`15.4.x-scala2.12` LTS, `m5d.large`) is created for each run. dbt only runs the CLI and sends SQL to Snowflake, so worker nodes would be wasted cost.
- **Task:** a `dbt_task` that runs `dbt deps` then `dbt build --target prod`, with `dbt-snowflake` installed from PyPI.
- **Code:** pulled from Git on the `main` branch.
- **Overlap:** only one run at a time, with a 2-hour timeout.

**Credentials:** the account, user and password come from a Databricks secret scope called `dbt-snowflake`, passed in as environment variables. `profiles.yml` reads those variables. I put it in `databricks/` rather than the repo root because dbt checks the current directory first, and a root copy would override developers' own `~/.dbt/profiles.yml`.

**Before you deploy, fill in these placeholders:**
1. **Repo URL:** `git_url` is a placeholder because this repo has no remote.
2. **Secrets:** create the scope and keys:
   ```
   databricks secrets create-scope dbt-snowflake
   databricks secrets put-secret dbt-snowflake account   # likewise: user, password
   ```
3. **Snowflake settings:** `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE` and `SNOWFLAKE_SCHEMA` are guesses. Set them to your real values.
4. **Node type:** `m5d.large` exists only on AWS. Use `Standard_DS3_v2` on Azure or `n2-standard-4` on GCP.

Then create the job with:
```
databricks jobs create --json @databricks/dbt_daily_job.json
```

If your Snowflake account requires key-pair login, replace `password` in the profile with `private_key` and store the key as a secret. I haven't committed anything.