# pipeline-fleet

Airflow 3.3 deployment that turns YAML pipeline configs into DAGs.

- `dags/pipeline_factory.py`: one DAG per `configs/pipelines/*.yaml`. Each step
  becomes a task; `depends_on` lists the steps it waits for.
- `configs/registry.yaml`: team and dataset registry exported by the platform
  team on every deploy (owners, on-call, retry defaults, registered tables).
  Do not edit it by hand.
- `pools.json`: Airflow pools; the deploy runs `airflow pools import pools.json`.
- `output/`: where the stand-in `run_step` records which steps ran.

Pipeline config fields: `name` (the dag_id), `team`, `tier` (`critical` or
`standard`), `description`,
`schedule.hour`, `schedule.days` (cron day-of-week, default `*`), optional
`schedule.minute` (otherwise the factory picks one to spread the load),
optional `owners` (added to the team's owners), optional `retries` (otherwise
the team default) and `steps` (`name`, `table`, `depends_on`).

Local run: `airflow dags test billing_carriers 2026-03-02`.
