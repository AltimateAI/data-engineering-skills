# claims-pipelines

Health-claims intake and service-date marts. Deployed with
`dags_folder=dags/` and `plugins_folder=plugins/` (locally:
`export AIRFLOW__CORE__PLUGINS_FOLDER=$PWD/plugins`). The clearing-house drop is
the `claims_export` connection (`fs` type, `{"export_dir": ...}` extra);
production defines it as
`AIRFLOW_CONN_CLAIMS_EXPORT='{"conn_type": "fs", "extra": {"export_dir": "/srv/claims/export"}}'`
(locally, point it at `data/`). Times are UTC.

| DAG | Schedule | What it does |
|---|---|---|
| `claims_intake_hourly` | hourly | Appends the claims received during the hour to their service-date partition, `output/lake/claims/service_date=<day>/`, and attaches each touched partition to the `claims-by-service-date` alias with its new-claim count |
| `claims_service_date_marts` | on the `claims-by-service-date` alias | Rebuilds `output/marts/claims_by_service_date/<day>.csv` for exactly the partitions in the triggering events, writes a numbered rebuild record (new claims per partition) to `output/marts/rebuilds/`, and appends the partition list to `output/marts/_READY_PARTITIONS` |
| `provider_directory_daily` | 03:00 | Snapshots the previous day's provider directory to `output/lake/providers/<day>.csv`, with `<day>.status` saying whether it changed since the previous snapshot; its XCom is the directory version |
| `denials_digest_daily` | 07:00 | Denied claims of the previous service date per provider, named from the latest directory snapshot at or before that date: `output/digests/<day>.csv` |
| `claims_reprocess` | manual | See runbook |

## Ops runbook

- **`claims_reprocess`**: from the ops box,
  `airflow dags trigger claims_reprocess --conf '{"service_date": "YYYY-MM-DD"}'`
  (no logical date).
  It lands every claim of that service date received before the moment of
  the trigger that the partition is missing (file
  `received_reprocess_<trigger time, yyyymmddThhmm>.csv`), the marts for
  that date are rebuilt, and the recheck is logged with the trigger time in
  `output/marts/_RECHECK_LOG`.

`data/` stands in for the clearing-house export drop.
