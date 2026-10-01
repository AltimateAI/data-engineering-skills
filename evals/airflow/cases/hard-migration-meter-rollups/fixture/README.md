# metering-pipelines

Smart-meter ingestion and billing. Deployed with `dags_folder=dags/` and
`plugins_folder=plugins/` (locally: `export AIRFLOW__CORE__PLUGINS_FOLDER=$PWD/plugins`).
Finance's invoice dropbox comes from the `[metering] invoice_dropbox` option
(production sets `AIRFLOW__METERING__INVOICE_DROPBOX`). All times are UTC.

| DAG | Schedule | What it does |
|---|---|---|
| `readings_<region>_hourly` (one per region in `config/regions.json`) | hourly | Lands the readings of the hour that just ended into `output/lake/readings/<region>/<YYYYMMDDTHH>.csv` and updates the region's dataset |
| `usage_rollup` | when **every** region has landed new readings | Re-aggregates kWh per meter and hour, for all regions, over the span from the start of the earliest hour covered by the regional loads that triggered the run to the end of the latest one. Several loads landing close together are batched into one run. Writes `output/rollup/usage_<first hour>_<end hour>.csv` and a `.json` manifest with the raw row counts each region delivered to that run |
| `tariffs_daily` | 01:00 | Syncs the previous day's tariffs plus the day-ahead tariffs into `output/lake/tariffs/<day>.csv` |
| `billing_daily` | 02:30 | Bills the previous day (latest rollup wins for an hour) into `output/billing/<day>.csv`, then publishes it to the dropbox as `INV-<yyyymmdd>.csv` |
| `meter_registry_daily` | daily | Exports the registry snapshot of the previous day to `output/registry/<day>.json` (`registry_version` Variable, default `2026.1`) |

## Ops runbook (manual runs)

On-call starts these from the ops box with the plain CLI trigger, no logical
date and no config (`airflow dags trigger <dag_id>`); the ops scripts do the
same through the REST API.

- **`billing_daily`**: `airflow dags trigger billing_daily` re-bills and re-publishes the **latest
  closed billing day** (the day the most recent scheduled run billed), e.g.
  after late readings were rolled up.
- **`tariffs_daily`**: `airflow dags trigger tariffs_daily` pulls **today's** and tomorrow's
  tariffs immediately when the utility publishes a correction.

`data/` stands in for the utility and meter-head-end exports.
