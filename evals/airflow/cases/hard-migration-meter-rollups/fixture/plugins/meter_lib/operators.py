"""Operators shared by the metering DAGs."""

from __future__ import annotations

import csv
from pathlib import Path

import pendulum
from airflow.models import BaseOperator

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class CsvSliceOperator(BaseOperator):
    """Copy the rows of ``source`` whose ``ts_column`` (UTC) falls in [start, end) to ``target``.

    Paths are relative to the project root. Each outlet dataset gets an event
    whose ``extra`` records how many rows were landed.
    """

    template_fields = ("source", "target", "start", "end")
    ui_color = "#e8f4ea"

    def __init__(
        self,
        *,
        source: str,
        target: str,
        ts_column: str,
        start: str = "{{ data_interval_start }}",
        end: str = "{{ data_interval_end }}",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.source = source
        self.target = target
        self.ts_column = ts_column
        self.start = start
        self.end = end

    def execute(self, context):
        lo, hi = pendulum.parse(self.start), pendulum.parse(self.end)
        with (PROJECT_ROOT / self.source).open(newline="") as fh:
            reader = csv.DictReader(fh)
            fields = reader.fieldnames
            rows = [r for r in reader if lo <= pendulum.parse(r[self.ts_column], tz="UTC") < hi]
        target = PROJECT_ROOT / self.target
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        for dataset in self.outlets:
            context["outlet_events"][dataset.uri].extra = {"rows": len(rows)}
        self.log.info("Landed %d rows from %s into %s", len(rows), self.source, self.target)
        return len(rows)
