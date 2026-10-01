"""Operators shared by the ledger DAGs."""

from __future__ import annotations

import csv
import json

from airflow.sdk import BaseOperator

from ledger_lib import PROJECT_ROOT


class DuckDbSqlOperator(BaseOperator):
    """Run a templated DuckDB query and write its result to ``target`` (CSV, relative to the project).

    Next to the CSV, ``<name>.meta.json`` records the row count and whether the run
    was started by the scheduler or by a person (the auditors ask for this).
    """

    template_fields = ("sql", "target")
    template_ext = (".sql",)
    template_fields_renderers = {"sql": "sql"}
    ui_color = "#fff3c4"

    def __init__(self, *, sql: str, target: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sql = sql
        self.target = target

    def execute(self, context):
        import duckdb

        path = PROJECT_ROOT / self.target
        path.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect()
        try:
            rel = con.sql(self.sql)
            columns, rows = rel.columns, rel.fetchall()
        finally:
            con.close()
        with path.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(columns)
            writer.writerows(rows)
        dag_run = context["dag_run"]
        meta = {"rows": len(rows), "started_by": "scheduler" if dag_run.run_type in ("scheduled", "backfill") else "operator"}
        path.with_suffix(".meta.json").write_text(json.dumps(meta, sort_keys=True) + "\n")
        self.log.info("Wrote %d rows to %s", len(rows), self.target)
        return len(rows)
