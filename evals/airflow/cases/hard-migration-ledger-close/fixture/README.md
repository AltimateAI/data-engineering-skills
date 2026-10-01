# ledger-pipelines

General-ledger ingestion, daily close and reporting. Deployed with
`dags_folder=dags/` and `plugins_folder=plugins/` (locally:
`export AIRFLOW__CORE__PLUGINS_FOLDER=$PWD/plugins`). The plugin registers the
business-day timetable and the `macros.ledger.*` template macros. The
reporting currency comes from the `[ledger] base_currency` option (production
sets `AIRFLOW__LEDGER__BASE_CURRENCY=USD`). Times are UTC unless noted.

| DAG | Schedule | What it does |
|---|---|---|
| `gl_postings_hourly` | hourly | Extracts every posting that arrived since the previous extract into `output/postings/batch_<hour end>.csv`; each posting lands exactly once |
| `daily_close` | every business day (Mon-Fri), after the day ends | Net movements of the day per account (`sql/daily_close.sql`) and rolled balances: `output/close/<day>/` |
| `fx_revaluation_daily` | 06:00 | Revalues balances booked up to the end of the previous day at that day's rate: `output/fx/revaluation_<yyyymmdd>.csv` |
| `close_report_weekly` | Mondays 07:00 | Net movement over the previous week's closed days, compared with the previous weekly report: `output/reports/week_<week start>.csv` |
| `vendor_payments_weekday` | 18:00 New York time, Mon-Fri | Pays the payables booked since the previous payment run (Monday's run covers the weekend): `output/payments/<ds>.csv` |
| `ledger_housekeeping` | every 12 hours | Counts the extracted batches for the storage audit: `output/housekeeping/batches_<ts>.txt` |

Every SQL output gets a `.meta.json` audit record saying whether the scheduler
or a person started the run.

## Ops runbook (manual runs)

On-call starts manual runs from the ops box with the plain CLI trigger, no
logical date and no config (`airflow dags trigger <dag_id>`).

- **`daily_close`**: when postings for an already closed business day arrive
  late, run `airflow dags trigger daily_close`. It re-closes the **latest business day that has
  ended** (on a Monday morning that is the previous Friday) and the audit
  record shows it was started by a person.

`data/` stands in for the ERP exports.
