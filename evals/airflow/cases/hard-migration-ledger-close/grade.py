"""Grader for hard-migration-ledger-close.

The fixture is an Airflow 2.11 general-ledger project: a custom business-day
timetable and a macro registered by a plugin, a DuckDB SQL operator with
``.sql`` templates (removed context keys, ``conf``, plugin macro) that records
``dag_run.external_trigger``, an hourly XCom-cursor extract, a weekly report
that receives ``prev_ds`` as a TaskFlow argument, a New York business-day cron
and a ``timedelta`` schedule.

The original is replayed in the 2.11 env and the agent's project in the 3.3 env
(task code under the Airflow 3 worker's metadata-DB block) with the same
scheduled runs and a CLI trigger of ``daily_close`` (no logical date on 3.x);
every file under ``output/`` must match. See ``hardsim`` for the replay.
"""

from __future__ import annotations

import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CASE_DIR))
import hardsim as hs  # noqa: E402

DAG_SHAPES = {
    "gl_postings_hourly": ({"extract"}, []),
    "daily_close": ({"net_movements", "roll_balances"}, [["net_movements", "roll_balances"]]),
    "fx_revaluation_daily": ({"revalue"}, []),
    "close_report_weekly": ({"weekly_report"}, []),
    "vendor_payments_weekday": ({"payment_run"}, []),
    "ledger_housekeeping": ({"inventory"}, []),
}
STEPS = [
    ["gl_postings_hourly", "2026-03-05T01:00:00+00:00"],
    ["gl_postings_hourly", "2026-03-05T02:00:00+00:00"],
    ["gl_postings_hourly", "2026-03-05T03:00:00+00:00"],
    ["ledger_housekeeping", "2026-03-05T12:00:00+00:00"],
    ["fx_revaluation_daily", "2026-03-05T06:00:00+00:00"],
    ["fx_revaluation_daily", "2026-03-06T06:00:00+00:00"],
    ["daily_close", "2026-03-03T00:00:00+00:00"],
    ["daily_close", "2026-03-04T00:00:00+00:00"],
    ["daily_close", "2026-03-05T00:00:00+00:00"],
    ["daily_close", "2026-03-06T00:00:00+00:00"],
    ["daily_close", "2026-03-07T00:00:00+00:00"],
    ["vendor_payments_weekday", "2026-03-06T23:00:00+00:00"],  # Fri 18:00 EST
    ["vendor_payments_weekday", "2026-03-09T22:00:00+00:00"],  # Mon 18:00 EDT (DST began 03-08)
    ["close_report_weekly", "2026-03-09T07:00:00+00:00"],
    ["daily_close", hs.trigger("2026-03-09T09:00:00+00:00")],
    ["close_report_weekly", "2026-03-16T07:00:00+00:00"],
]
AREAS = [
    ("hourly extracts land every posting exactly once, in the same batches", ("postings/",)),
    ("daily close (scheduled runs and the CLI-triggered re-close) writes the same files and audit records", ("close/",)),
    ("FX revaluation matches", ("fx/",)),
    ("weekly close reports match", ("reports/",)),
    ("vendor payment runs pay the same postings under the same names", ("payments/",)),
    ("housekeeping inventory files match", ("housekeeping/",)),
]


def env_extra(ws: Path) -> dict:
    return {"AIRFLOW__CORE__PLUGINS_FOLDER": str(ws / "plugins"), "AIRFLOW__LEDGER__BASE_CURRENCY": "USD"}


if __name__ == "__main__":
    hs.grade_project(CASE_DIR, dag_shapes=DAG_SHAPES, steps=STEPS, areas=AREAS, env_extra=env_extra)
