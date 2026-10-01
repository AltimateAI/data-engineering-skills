"""Registers the ledger timetable and the ``macros.ledger.*`` template macros."""

from airflow.plugins_manager import AirflowPlugin

from ledger_lib.workdays import WorkdayTimetable, fiscal_period


class LedgerPlugin(AirflowPlugin):
    name = "ledger"
    macros = [fiscal_period]
    timetables = [WorkdayTimetable]
