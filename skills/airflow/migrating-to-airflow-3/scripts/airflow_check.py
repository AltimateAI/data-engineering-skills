#!/usr/bin/env python3
"""Check Airflow DAG files: import errors, schedule preview, and static rules.

Run it with the Python interpreter of the project's Airflow environment. It uses
only the standard library plus the Airflow that is already installed there.

    python airflow_check.py [DAGS_PATH ...] [--dag-id ID] [--runs N]
                            [--from DATE] [--json]

What it reports:
  * import errors from a real DagBag parse (the same code path the scheduler uses)
  * per DAG: schedule, timetable class, catchup, start_date, task count and the
    next N scheduled runs (run_after, logical_date, data interval) computed with
    the timetable API, so no scheduler or metadata DB is needed
  * static findings from an AST scan of the DAG files, adjusted to the Airflow
    major version (removed context keys, parse-time I/O, dynamic DAG arguments...)

Isolation: when AIRFLOW_HOME is unset a temporary one is used. The metadata DB
is always pointed at a throwaway sqlite file and example DAGs are disabled, so a
real metadata database is never touched.

Exit codes:
  0  clean (warnings allowed)
  1  at least one DAG file failed to import
  2  no import errors, but at least one static finding with severity "error"
  3  usage or environment error (bad arguments, missing path, Airflow missing,
     --dag-id not found)
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import sys
import tempfile
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXIT_OK, EXIT_IMPORT, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2, 3
MAX_RUNS = 50
MAX_FINDINGS = 200
MAX_DAGS = 200
MAX_FILES = 2000
MAX_WARNINGS_PER_DAG = 20
MAX_PARSE_WARNINGS = 50
ERROR_MAX_CHARS = 1500
ERROR_MAX_LINES = 20
CATCHUP_COUNT_CAP = 1000
DEFAULT_SENSOR_TIMEOUT_S = 7 * 24 * 3600
SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", ".tox", ".mypy_cache"}
TEMPLATE_EXTS = {".sql", ".sh", ".bash", ".j2", ".jinja", ".hql"}

# Context keys removed in Airflow 3.0, with the replacement to suggest.
REMOVED_CONTEXT_KEYS = {
    "execution_date": "logical_date (on 3.x cron/timedelta schedules this equals the run time, "
    "not the start of the previous period)",
    "next_execution_date": "data_interval_end",
    "prev_execution_date": "the logical_date of the previous schedule tick, computed from the "
    "timetable (prev_data_interval_start_success means the previous *successful* run, which "
    "differs after failures)",
    "prev_execution_date_success": "prev_data_interval_start_success",
    "next_ds": "data_interval_end | ds, or macros.ds_add(ds, 1)",
    "next_ds_nodash": "data_interval_end | ds_nodash",
    "prev_ds": "the ds of the previous schedule tick (2.x: previous_schedule(logical_date); the "
    "same day on manual runs): macros.ds_add(ds, -1) only for daily schedules, -7 weekly, computed "
    "from the timetable for hourly/monthly/weekday crons",
    "prev_ds_nodash": "the previous schedule tick's ds_nodash (see prev_ds; not always ds - 1 day)",
    "yesterday_ds": "macros.ds_add(ds, -1)",
    "yesterday_ds_nodash": "macros.ds_format(macros.ds_add(ds, -1), '%Y-%m-%d', '%Y%m%d')",
    "tomorrow_ds": "macros.ds_add(ds, 1)",
    "tomorrow_ds_nodash": "macros.ds_format(macros.ds_add(ds, 1), '%Y-%m-%d', '%Y%m%d')",
    "triggering_dataset_events": "triggering_asset_events",
}
_REMOVED_ALT = "|".join(sorted(REMOVED_CONTEXT_KEYS, key=len, reverse=True))
JINJA_BLOCK_RE = re.compile(r"\{\{(.*?)\}\}|\{%(.*?)%\}", re.S)
JINJA_REMOVED_RE = re.compile(r"(?<![\w.'\"])(" + _REMOVED_ALT + r")\b")
JINJA_RUN_ATTR_RE = re.compile(r"\b(?:dag_run|ti|task_instance)\.execution_date\b")
JINJA_XCOM_NO_IDS_RE = re.compile(r"xcom_pull\(\s*(?:key\s*=\s*(['\"])[^'\"]*\1\s*)?\)")
JINJA_RUN_DATE_RE = re.compile(
    r"(?<![\w.'\"])(ds|ds_nodash|ts|ts_nodash|logical_date|data_interval_start|data_interval_end)\b"
)
RUN_DATE_KEYS = {"ds", "ds_nodash", "ts", "ts_nodash", "logical_date",
                 "data_interval_start", "data_interval_end"}

# Names Airflow injects into TaskFlow / python_callable parameters from the context.
CONTEXT_KEYS = {
    "conf", "dag", "dag_run", "data_interval_end", "data_interval_start", "ds", "ds_nodash",
    "inlets", "logical_date", "macros", "map_index_template", "outlets", "params",
    "prev_data_interval_end_success", "prev_data_interval_start_success", "prev_end_date_success",
    "prev_start_date_success", "run_after", "run_id", "task", "task_instance",
    "task_instance_key_str", "templates_dict", "test_mode", "ti", "triggering_asset_events",
    "ts", "ts_nodash", "ts_nodash_with_tz", "var", "conn", "outlet_events", "inlet_events",
} | set(REMOVED_CONTEXT_KEYS)

NOW_CALLS = ("datetime.now", "datetime.utcnow", "datetime.today", "date.today", "pendulum.now",
             "pendulum.today", "pendulum.yesterday", "pendulum.tomorrow", "timezone.utcnow")
DYNAMIC_CALLS = NOW_CALLS + ("time.time", "uuid.uuid1", "uuid.uuid4", "days_ago")
DYNAMIC_PREFIXES = ("random.",)
DATE_DERIVING_ATTRS = {"date", "strftime", "replace", "subtract", "add", "start_of", "end_of",
                       "to_date_string", "format", "day", "month", "year", "weekday",
                       "isoweekday", "hour", "timestamp"}
DURATION_CALLS = ("timedelta", "relativedelta", "duration", "Duration")
PARSE_IO_CALLS = (
    "Variable.get", "Variable.set", "Variable.setdefault", "BaseHook.get_connection",
    "Connection.get", "Connection.get_connection_from_secrets", "create_session",
    "settings.Session", "urllib.request.urlopen", "urlopen", "socket.create_connection",
    "psycopg2.connect", "pymysql.connect", "sqlite3.connect", "duckdb.connect",
    "snowflake.connector.connect", "pyodbc.connect", "mysql.connector.connect",
    "redshift_connector.connect",
) + tuple(f"{m}.{v}" for m in ("requests", "httpx")
          for v in ("get", "post", "put", "patch", "delete", "head", "request"))
PARSE_IO_METHODS = {"get_records", "get_first", "get_pandas_df", "get_df", "get_conn",
                    "get_connection"}
AIRFLOW_MODELS = {"DagRun", "TaskInstance", "XCom", "DagModel", "Log", "DagTag", "Pool",
                  "Variable", "Connection", "SlaMiss", "TaskReschedule", "Trigger"}
DB_IN_TASK_CALLS = ("create_session", "settings.Session", "DagRun.find")
REMOVED_DAG_KWARGS_3 = {
    "schedule_interval": "use schedule=",
    "timetable": "pass the timetable object to schedule=",
    "concurrency": "use max_active_tasks=",
}
_AST_INDEX = getattr(ast, "Index", ())
TRIGGER_TIMETABLES = {"CronTriggerTimetable", "DeltaTriggerTimetable",
                      "MultipleCronTriggerTimetable"}


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------


def _major(version: str | None) -> int | None:
    if not version:
        return None
    m = re.match(r"\s*(\d+)", str(version))
    return int(m.group(1)) if m else None


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _rel(path: str | os.PathLike | None) -> str | None:
    if path is None:
        return None
    try:
        rel = os.path.relpath(str(path), os.getcwd())
    except ValueError:
        return str(path)
    return str(path) if rel.startswith("..") else rel


def _trim_error(text: str) -> str:
    lines = [ln for ln in str(text).rstrip().splitlines() if ln.strip()]
    tail = "\n".join(lines[-ERROR_MAX_LINES:])
    return tail if len(tail) <= ERROR_MAX_CHARS else "..." + tail[-ERROR_MAX_CHARS:]


def _matches(name: str | None, patterns) -> str | None:
    if not name:
        return None
    for pat in patterns:
        if name == pat or name.endswith("." + pat):
            return pat
    return None


def installed_airflow_version() -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - Python < 3.8
        return None
    for dist in ("apache-airflow", "apache-airflow-core"):
        try:
            return version(dist)
        except PackageNotFoundError:
            continue
    return None


# ----------------------------------------------------------------------------
# Static AST scan
# ----------------------------------------------------------------------------


class FileScan:
    """Static rules for one Python DAG file; ``major`` is the target Airflow major."""

    def __init__(self, path: Path, source: str, major: int | None):
        self.path = path
        self.source = source
        self.major = major
        self.findings: list[dict] = []
        self._seen: set[tuple] = set()
        self._dyn_seen: set[int] = set()

    # -- reporting -----------------------------------------------------------
    def add(self, line: int, rule: str, message: str, severity: str = "error") -> None:
        key = (line, rule, message)
        if key in self._seen:
            return
        self._seen.add(key)
        self.findings.append({"file": _rel(self.path), "line": int(line or 1), "rule": rule,
                              "severity": severity, "message": message})

    # -- name resolution -----------------------------------------------------
    def dotted(self, node) -> str | None:
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Call):  # e.g. pendulum.now().subtract -> "pendulum.now().subtract"
            inner = self.dotted(node.func)
            if inner is None:
                return None
            parts.append(inner + "()")
            return ".".join(reversed(parts))
        if not isinstance(node, ast.Name):
            return None
        head = self.aliases.get(node.id, node.id)
        parts.append(head)
        return ".".join(reversed(parts))

    def call_name(self, call: ast.Call) -> str | None:
        return self.dotted(call.func)

    # -- setup ---------------------------------------------------------------
    def _index(self, tree: ast.Module) -> None:
        self.aliases: dict[str, str] = {}
        self.parents: dict[ast.AST, ast.AST] = {}
        self.in_func: dict[ast.AST, bool] = {}
        self.in_main: dict[ast.AST, bool] = {}
        self.module_assign: dict[str, ast.AST] = {}
        self.docstrings: set[int] = set()
        self.guarded: set[int] = set()  # imports inside try/except ImportError (version shims)
        for node in ast.walk(tree):
            if isinstance(node, ast.Try) and any(self._catches_import_error(h) for h in node.handlers):
                for stmt in node.body:
                    for sub in ast.walk(stmt):
                        if isinstance(sub, (ast.Import, ast.ImportFrom)):
                            self.guarded.add(id(sub))
            for child in ast.iter_child_nodes(node):
                self.parents[child] = node
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname:
                        self.aliases[a.asname] = a.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    self.aliases[a.asname or a.name] = f"{node.module}.{a.name}"
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = node.body
                if body and isinstance(body[0], ast.Expr) and isinstance(
                        getattr(body[0], "value", None), ast.Constant) and isinstance(
                        body[0].value.value, str):
                    self.docstrings.add(id(body[0].value))
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name):
                        self.module_assign[tgt.id] = stmt.value
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value:
                self.module_assign[stmt.target.id] = stmt.value
        self._mark_scope(tree, False, False)

    def _enclosing_func(self, node):
        """Innermost function/lambda whose *body* contains node (decorators/defaults excluded)."""
        child, parent = node, self.parents.get(node)
        while parent is not None:
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)) and child in parent.body:
                return parent
            if isinstance(parent, ast.Lambda) and child is parent.body:
                return parent
            child, parent = parent, self.parents.get(parent)
        return None

    def _is_dag_decorator(self, dec) -> bool:
        target = dec.func if isinstance(dec, ast.Call) else dec
        name = self.dotted(target) or ""
        last = name.split(".")[-1]
        return last == "dag" and (name.startswith("airflow") or name == "dag")

    def _find_parse_time_funcs(self, tree) -> None:
        """Functions whose bodies run while the file is parsed.

        Seeds: @dag-decorated functions (their body builds the DAG at parse time). Then any
        function in this file called by name from module level or from a parse-time body
        (DAG factories, helpers), transitively. @task functions are excluded: calling them
        at parse time only creates a task.
        """
        funcs: dict[str, list] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs.setdefault(node.name, []).append(node)
        self.parse_time_funcs: dict[ast.AST, str] = {}
        for defs in funcs.values():
            for f in defs:
                if any(self._is_dag_decorator(d) for d in f.decorator_list):
                    self.parse_time_funcs[f] = f"@dag function `{f.name}`"
        calls = [(c, self._enclosing_func(c)) for c in ast.walk(tree)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in funcs]
        changed = True
        while changed:
            changed = False
            for call, scope in calls:
                if self.in_main.get(call, False):
                    continue
                if scope is not None and scope not in self.parse_time_funcs:
                    continue
                for f in funcs[call.func.id]:
                    if f in self.parse_time_funcs or any(
                            self.is_task_decorator(d) for d in f.decorator_list):
                        continue
                    self.parse_time_funcs[f] = f"`{f.name}()`, called while the file is parsed"
                    changed = True

    def _mark_scope(self, node, in_func: bool, in_main: bool) -> None:
        self.in_func[node] = in_func
        self.in_main[node] = in_main
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            outer = list(node.decorator_list) + list(node.args.defaults) + [
                d for d in node.args.kw_defaults if d is not None]
            for child in outer:
                self._mark_scope(child, in_func, in_main)
            for child in node.body:
                self._mark_scope(child, True, in_main)
            return
        if isinstance(node, ast.Lambda):
            for child in list(node.args.defaults) + [d for d in node.args.kw_defaults if d]:
                self._mark_scope(child, in_func, in_main)
            self._mark_scope(node.body, True, in_main)
            return
        if isinstance(node, ast.If) and self._is_main_guard(node.test):
            self._mark_scope(node.test, in_func, in_main)
            for child in node.body:
                self._mark_scope(child, in_func, True)
            for child in node.orelse:
                self._mark_scope(child, in_func, in_main)
            return
        for child in ast.iter_child_nodes(node):
            self._mark_scope(child, in_func, in_main)

    @staticmethod
    def _catches_import_error(handler) -> bool:
        if handler.type is None:
            return True
        types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        names = {t.id if isinstance(t, ast.Name) else getattr(t, "attr", None) for t in types}
        return bool(names & {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"})

    @staticmethod
    def _is_main_guard(test) -> bool:
        return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                and test.left.id == "__name__" and len(test.comparators) == 1
                and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__")

    def is_task_decorator(self, dec) -> bool:
        target = dec.func if isinstance(dec, ast.Call) else dec
        name = self.dotted(target) or ""
        return "task" in name.split(".")

    def is_dag_call(self, call: ast.Call) -> bool:
        name = self.call_name(call) or ""
        last = name.split(".")[-1]
        if last == "DAG":
            return True
        return last == "dag" and (name.startswith("airflow") or name == "dag")

    def _collect(self, tree) -> None:
        self.task_funcs: dict[str, ast.AST] = {}
        self.callable_names: set[str] = set()
        self.ctx_names = {"context", "ctx"}
        self.default_args_dicts: list[ast.Dict] = []
        self.dag_calls: list[ast.Call] = []
        self.bare_dag_decorators: list[ast.AST] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(self.is_task_decorator(d) for d in node.decorator_list):
                    self.task_funcs[node.name] = node
                if node.args.kwarg is not None:
                    self.ctx_names.add(node.args.kwarg.arg)
                for dec in node.decorator_list:
                    if isinstance(dec, (ast.Name, ast.Attribute)) and not isinstance(dec, ast.Call):
                        name = self.dotted(dec) or ""
                        last = name.split(".")[-1]
                        if last == "dag" and (name.startswith("airflow") or name == "dag"):
                            self.bare_dag_decorators.append(dec)
            elif isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "python_callable" and isinstance(kw.value, ast.Name):
                        self.callable_names.add(kw.value.id)
                    if kw.arg == "default_args" and isinstance(kw.value, ast.Dict):
                        self.default_args_dicts.append(kw.value)
                if self.is_dag_call(node):
                    self.dag_calls.append(node)
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                if (self.call_name(node.value) or "").endswith("get_current_context"):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            self.ctx_names.add(tgt.id)
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(
                    getattr(node, "value", None), ast.Dict):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(t, ast.Name) and "default_args" in t.id for t in targets):
                    self.default_args_dicts.append(node.value)

    # -- driver --------------------------------------------------------------
    def run(self) -> list[dict]:
        try:
            tree = ast.parse(self.source, filename=str(self.path))
        except SyntaxError as exc:
            self.add(exc.lineno or 1, "syntax-error", f"SyntaxError: {exc.msg}")
            return self.findings
        self._index(tree)
        self._collect(tree)
        self._find_parse_time_funcs(tree)
        v3 = self.major is not None and self.major >= 3
        v2 = self.major == 2
        run_date_lines: list = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) not in self.docstrings:
                    run_date_lines.append(self._scan_string(node.value, node.lineno, v3))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                self._check_import(node, v2)
            elif isinstance(node, ast.Call):
                self._check_call(node, v3)
            elif isinstance(node, ast.Subscript):
                run_date_lines.append(self._check_subscript(node, v3))
            elif isinstance(node, ast.Attribute):
                self._check_attribute(node, v3)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                run_date_lines.append(self._check_function(node, v3))
        for call in self.dag_calls:
            self._check_dag_call(call, v3)
        for dec in self.bare_dag_decorators:
            self._check_dag_kwargs(dec, {}, has_star=False, v3=v3)
        self._check_reserved_param_calls(tree, v2)
        for d in self.default_args_dicts:
            for k in d.keys:
                if v3 and isinstance(k, ast.Constant) and k.value == "sla":
                    self.add(k.lineno, "sla-ignored", self._sla_msg("default_args['sla']"))
        run_date_line = min((ln for ln in run_date_lines if ln), default=None)
        if v3 and run_date_line:
            self.add(run_date_line, "manual-run-dates",
                     "On Airflow >= 3.0 a run triggered manually or by an asset event can have "
                     "logical_date=None and data_interval_start/end=None, so ds/ts/logical_date/"
                     "data_interval_* fail or render empty. If manual runs must work, derive the "
                     "day from dag_run.run_after (always set) or a DAG param.", "warning")
        return self.findings

    # -- rules ---------------------------------------------------------------
    def _scan_string(self, text: str, lineno: int, v3: bool) -> int | None:
        if "{{" not in text and "{%" not in text:
            return None
        return scan_template_text(text, lineno, v3, self.add)

    def _check_import(self, node, v2: bool) -> None:
        if not v2 or id(node) in self.guarded:
            return
        mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
        for mod in mods:
            if mod == "airflow.sdk" or mod.startswith("airflow.sdk."):
                self.add(node.lineno, "sdk-import-on-2x",
                         f"`{mod}` exists only in Airflow >= 3.0; this project targets 2.x, so the "
                         "import fails. Use airflow.decorators / airflow.models / airflow.operators.")

    def _check_call(self, call: ast.Call, v3: bool) -> None:
        name = self.call_name(call) or ""
        kws = {kw.arg: kw for kw in call.keywords if kw.arg}
        top_level = not self.in_func.get(call, False) and not self.in_main.get(call, False)
        in_body = self.in_func.get(call, False) and not self.in_main.get(call, False)

        # xcom_pull without task_ids
        if isinstance(call.func, ast.Attribute) and call.func.attr == "xcom_pull":
            has_star = any(kw.arg is None for kw in call.keywords)
            if not call.args and "task_ids" not in kws and not has_star:
                if v3:
                    self.add(call.lineno, "xcom-pull-no-task-ids",
                             "xcom_pull() without task_ids pulls only from the current task on "
                             "Airflow >= 3.0, so it returns None here. Pass task_ids='<upstream>'.")
                elif self.major == 2:
                    self.add(call.lineno, "xcom-pull-no-task-ids",
                             "xcom_pull() without task_ids: Airflow 3 changes this to pull only from "
                             "the current task. Pass task_ids explicitly.", "warning")

        # parse-time I/O
        parse_scope = None
        if not top_level and not self.in_main.get(call, False):
            parse_scope = self.parse_time_funcs.get(self._enclosing_func(call))
        if top_level or parse_scope:
            hit = _matches(name, PARSE_IO_CALLS)
            if not hit and isinstance(call.func, ast.Attribute) and call.func.attr in PARSE_IO_METHODS:
                hit = call.func.attr
            if hit:
                where = f"inside {parse_scope}" if parse_scope else "at module level"
                self.add(call.lineno, "top-level-io",
                         f"`{hit}(...)` runs {where}, i.e. on every parse of this file by "
                         "the DAG processor: it slows parsing, hits the DB/secrets backend/network, "
                         "and parse-time failures become import errors (a default value only hides "
                         "this). Move it into the task, or use a template "
                         "({{ var.value.<key> }}, {{ conn.<conn_id>.host }}).")

        # DB access inside task code (3.x)
        if v3 and in_body:
            hit = _matches(name, DB_IN_TASK_CALLS)
            if not hit and name == "airflow.settings.Session":
                hit = "Session"
            if not hit and isinstance(call.func, ast.Attribute) and call.func.attr == "query":
                for arg in call.args:
                    an = self.dotted(arg) or ""
                    if an.startswith("airflow") and an.split(".")[-1] in AIRFLOW_MODELS:
                        hit = f"query({an.split('.')[-1]})"
            if hit:
                self.add(call.lineno, "db-access-in-task", self._db_msg(hit))

        # wall clock deciding data in tasks
        if in_body and _matches(name, NOW_CALLS) and self._derives_date(call):
            self.add(call.lineno, "wall-clock-in-task",
                     f"`{'.'.join(name.split('.')[-2:])}()` picks which data to process from the wall clock: retries, reruns, late runs "
                     "and backfills then process the wrong period. Derive dates from the run "
                     "(data_interval_start/end or logical_date; for manual runs on Airflow >= 3.0, "
                     "dag_run.run_after).", "warning")

        # removed / ignored kwargs (3.x)
        if v3:
            if "provide_context" in kws:
                self.add(call.lineno, "removed-kwarg",
                         "provide_context= was removed in Airflow 3.0 (TypeError: invalid "
                         "arguments). The context is always passed; delete the argument.")
            if "sla" in kws:
                self.add(kws["sla"].value.lineno, "sla-ignored", self._sla_msg("sla="))

        # poke sensors without timeout
        if name.split(".")[-1].endswith("Sensor"):
            self._check_sensor(call, kws, name.split(".")[-1])
        elif name.endswith("task.sensor"):
            self._check_sensor(call, kws, "@task.sensor")

    def _derives_date(self, call: ast.Call) -> bool:
        parent = self.parents.get(call)
        if isinstance(parent, ast.Attribute) and parent.attr in DATE_DERIVING_ATTRS:
            return True
        if isinstance(parent, ast.Compare):
            return True
        if isinstance(parent, ast.BinOp) and isinstance(parent.op, (ast.Add, ast.Sub)):
            other = parent.right if parent.left is call else parent.left
            for sub in ast.walk(other):
                if isinstance(sub, ast.Call) and _matches(self.call_name(sub), DURATION_CALLS):
                    return True
        return False

    def _check_sensor(self, call: ast.Call, kws: dict, cls: str, line: int | None = None) -> None:
        if any(kw.arg is None for kw in call.keywords):
            return
        mode = kws.get("mode")
        mode_val = mode.value.value if mode is not None and isinstance(mode.value, ast.Constant) else None
        if mode is not None and mode_val is None:
            return  # computed mode: unknown
        defer = kws.get("deferrable")
        if defer is not None and not (isinstance(defer.value, ast.Constant) and defer.value.value is False):
            return
        if mode_val == "reschedule" or "timeout" in kws:
            return
        for d in self.default_args_dicts:
            keys = {k.value for k in d.keys if isinstance(k, ast.Constant)}
            if "timeout" in keys:
                return
            for k, v in zip(d.keys, d.values):
                if isinstance(k, ast.Constant) and k.value == "mode" and isinstance(
                        v, ast.Constant) and v.value == "reschedule":
                    return
        self.add(line or call.lineno, "sensor-poke-no-timeout",
                 f"{cls} runs in poke mode without timeout=: it holds a worker slot for up to the "
                 "default 7-day timeout if the condition never becomes true. Set timeout= (seconds) "
                 "and prefer mode='reschedule' or deferrable=True for long waits.")

    def _check_subscript(self, node: ast.Subscript, v3: bool) -> int | None:
        key = node.slice
        if isinstance(key, _AST_INDEX):  # Python < 3.9 wraps subscripts
            key = key.value
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            return None
        if not self._is_context_expr(node.value):
            return None
        if v3 and key.value in REMOVED_CONTEXT_KEYS:
            self.add(node.lineno, "removed-context-key", _removed_msg(key.value, "context lookup"))
        return node.lineno if key.value in RUN_DATE_KEYS else None

    def _is_context_expr(self, node) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self.ctx_names
        if isinstance(node, ast.Call):
            return (self.call_name(node) or "").endswith("get_current_context")
        return False

    def _check_attribute(self, node: ast.Attribute, v3: bool) -> None:
        if not v3:
            return
        # context.get("execution_date")
        parent = self.parents.get(node)
        if node.attr == "get" and isinstance(parent, ast.Call) and parent.func is node \
                and self._is_context_expr(node.value) and parent.args \
                and isinstance(parent.args[0], ast.Constant) \
                and parent.args[0].value in REMOVED_CONTEXT_KEYS:
            self.add(node.lineno, "removed-context-key",
                     _removed_msg(parent.args[0].value, "context lookup"))
        if node.attr == "execution_date":
            base = node.value
            base_name = base.id if isinstance(base, ast.Name) else None
            if isinstance(base, ast.Subscript) and self._is_context_expr(base.value):
                sl = base.slice.value if isinstance(base.slice, _AST_INDEX) else base.slice
                base_name = sl.value if isinstance(sl, ast.Constant) else None
            if base_name in {"dag_run", "ti", "task_instance", "dr"}:
                self.add(node.lineno, "removed-context-key",
                         f"{base_name}.execution_date does not exist on Airflow >= 3.0. Use "
                         f"{base_name}.logical_date (None for manual runs) or dag_run.run_after.")

    def _check_function(self, node, v3: bool) -> int | None:
        is_task = node.name in self.task_funcs or node.name in self.callable_names
        if not is_task:
            return None
        params = [a.arg for a in node.args.args + node.args.kwonlyargs]
        if v3:
            for p in params:
                if p in REMOVED_CONTEXT_KEYS:
                    self.add(node.lineno, "removed-context-key",
                             _removed_msg(p, f"parameter of task callable `{node.name}`"))
        if any(p in RUN_DATE_KEYS for p in params):
            return node.lineno
        return None

    def _check_reserved_param_calls(self, tree, v2: bool) -> None:
        """Values passed to TaskFlow parameters named like context keys.

        Checked on 2.11 and 3.3: `.expand()`/`.partial()` on such a parameter is an import error
        on both; a positional value fails at run time on 2.x ("... reserved") and works on 3.x;
        a keyword value works on both.
        """
        reserved = {}
        for fname, fn in self.task_funcs.items():
            args = [a.arg for a in fn.args.args]
            kwonly = [a.arg for a in fn.args.kwonlyargs]
            hits = {p for p in args + kwonly if p in CONTEXT_KEYS}
            if hits:
                reserved[fname] = (args, hits)
        if not reserved:
            return
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id in reserved:
                if not v2:
                    continue
                args, hits = reserved[func.id]
                passed = {args[i] for i in range(min(len(node.args), len(args))) if args[i] in hits}
                for p in sorted(passed):
                    self.add(node.lineno, "reserved-context-param",
                             f"Task `{func.id}` receives a positional value for parameter `{p}`, "
                             f"which is a context key. On Airflow 2.x the task fails with \"The key "
                             f"'{p}' in args is a part of kwargs and therefore reserved\". Rename "
                             "the parameter (or pass it by keyword).")
            elif isinstance(func, ast.Attribute) and func.attr in {"expand", "partial"} \
                    and isinstance(func.value, ast.Name) and func.value.id in reserved:
                _, hits = reserved[func.value.id]
                for p in sorted({kw.arg for kw in node.keywords if kw.arg} & hits):
                    self.add(node.lineno, "reserved-context-param",
                             f"`{func.value.id}.{func.attr}({p}=...)`: `{p}` is a context key, so "
                             f"the DAG file fails to import (\"cannot call {func.attr}() on task "
                             f"context variable '{p}'\"). Rename the parameter.")

    def _check_dag_call(self, call: ast.Call, v3: bool) -> None:
        kws = {kw.arg: kw for kw in call.keywords if kw.arg}
        has_star = any(kw.arg is None for kw in call.keywords)
        # dynamic values in DAG arguments
        exprs = [("positional argument", a) for a in call.args] + [
            (f"`{kw.arg}`", kw.value) for kw in call.keywords if kw.arg]
        seen_calls = self._dyn_seen
        for label, expr in exprs:
            for sub_label, sub in self._expand_names(label, expr):
                for n in ast.walk(sub):
                    if isinstance(n, ast.Call) and id(n) not in seen_calls:
                        seen_calls.add(id(n))
                        cname = self.call_name(n) or ""
                        hit = _matches(cname, DYNAMIC_CALLS) or next(
                            (cname for p in DYNAMIC_PREFIXES if cname.startswith(p)), None)
                        if hit:
                            self.add(n.lineno, "dynamic-dag-arg",
                                     f"`{hit}()` in DAG argument {sub_label} is re-evaluated on "
                                     "every parse, so the DAG definition changes each time "
                                     "(Airflow >= 3.0 creates a new DAG version per parse; a moving "
                                     "start_date or dag_id can stop runs from being scheduled). Use "
                                     "a fixed value, e.g. pendulum.datetime(2024, 1, 1, tz='UTC').")
        if v3:
            for kw, fix in REMOVED_DAG_KWARGS_3.items():
                if kw in kws:
                    self.add(kws[kw].value.lineno, "removed-dag-kwarg",
                             f"DAG(..., {kw}=) was removed in Airflow 3.0 (TypeError at import); "
                             f"{fix}.")
            if "sla_miss_callback" in kws:
                self.add(kws["sla_miss_callback"].value.lineno, "sla-ignored",
                         self._sla_msg("sla_miss_callback="))
        self._check_dag_kwargs(call, kws, has_star, v3)

    def _expand_names(self, label, expr, depth: int = 2):
        """``expr`` plus module-level values it references by name (``default_args`` etc.)."""
        yield label, expr
        if depth <= 0:
            return
        for n in ast.walk(expr):
            if isinstance(n, ast.Name) and n.id in self.module_assign:
                value = self.module_assign[n.id]
                if value is not expr:
                    yield from self._expand_names(f"{label} (via `{n.id}`)", value, depth - 1)

    def _check_dag_kwargs(self, node, kws: dict, has_star: bool, v3: bool) -> None:
        if has_star or self.major is None:
            return
        line = node.lineno
        sched_kw = next((kws[k] for k in ("schedule", "schedule_interval", "timetable") if k in kws), None)
        if sched_kw is None:
            if v3:
                self.add(line, "schedule-missing",
                         "No schedule= given: on Airflow >= 3.0 the default is None, so this DAG "
                         "only runs when triggered. Pass schedule explicitly.", "warning")
                return
            self.add(line, "schedule-missing",
                     "No schedule given: Airflow 2.x defaults to a daily schedule with catchup=True "
                     "(Airflow 3 defaults to None). Pass schedule and catchup explicitly.", "warning")
            return
        elif isinstance(sched_kw.value, ast.Constant) and sched_kw.value.value is None:
            return
        if "catchup" not in kws:
            default = "False" if v3 else "True"
            self.add(line, "catchup-implicit",
                     f"catchup not set: it defaults to {default} on Airflow {'>= 3.0' if v3 else '2.x'} "
                     "(config catchup_by_default), and the default flipped between 2.x and 3.x. Set "
                     "catchup explicitly so backfill behaviour is intentional.", "warning")

    @staticmethod
    def _sla_msg(what: str) -> str:
        return (f"{what} is silently ignored on Airflow >= 3.0 (SLAs were removed; no error, no "
                "alert). Use a Deadline Alert (DAG(deadline=DeadlineAlert(...)), Airflow >= 3.1) "
                "or remove it.")

    @staticmethod
    def _db_msg(hit: str) -> str:
        return (f"`{hit}` inside task code: Airflow >= 3.0 blocks direct metadata-DB access from "
                "tasks, so this fails at runtime. Use the Task SDK (Variable, Connection, XCom, "
                "context['dag_run'] / context['ti']) or the REST API.")


def _removed_msg(key: str, where: str) -> str:
    return (f"`{key}` ({where}) was removed from the task context in Airflow 3.0; the DAG still "
            f"imports but the task fails at runtime. Use {REMOVED_CONTEXT_KEYS[key]}.")


def _is_filter(body: str, pos: int) -> bool:
    """True when the name at ``pos`` is used as a Jinja filter (``x | ds``)."""
    return body[:pos].rstrip().endswith("|")


def scan_template_text(text: str, lineno: int, v3: bool, add) -> int | None:
    """Jinja rules over a string; returns the line of the first run-date reference."""
    first_run_date = None
    for m in JINJA_BLOCK_RE.finditer(text):
        body = m.group(1) if m.group(1) is not None else m.group(2)
        line = lineno + text.count("\n", 0, m.start())
        if v3:
            for km in JINJA_REMOVED_RE.finditer(body):
                if not _is_filter(body, km.start()):
                    add(line, "removed-context-key", _removed_msg(km.group(1), "Jinja template"))
            for km in JINJA_RUN_ATTR_RE.finditer(body):
                add(line, "removed-context-key",
                    f"`{km.group(0)}` (Jinja template) does not exist on Airflow >= 3.0. Use "
                    "logical_date (None for manual runs) or dag_run.run_after.")
            if JINJA_XCOM_NO_IDS_RE.search(body):
                add(line, "xcom-pull-no-task-ids",
                    "xcom_pull() without task_ids in a template pulls only from the current task "
                    "on Airflow >= 3.0 and renders None. Pass task_ids='<upstream>'.")
        if first_run_date is None and any(
                not _is_filter(body, km.start()) for km in JINJA_RUN_DATE_RE.finditer(body)):
            first_run_date = line
    return first_run_date


def iter_files(paths: list[Path]):
    count = 0
    for base in paths:
        if base.is_file():
            yield base
            count += 1
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            for f in sorted(files):
                p = Path(root) / f
                if p.suffix == ".py" or p.suffix in TEMPLATE_EXTS:
                    yield p
                    count += 1
                    if count >= MAX_FILES:
                        return


def static_scan(paths: list[Path], major: int | None) -> tuple[list[dict], int]:
    findings: list[dict] = []
    n = 0
    for p in iter_files(paths):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n += 1
        if p.suffix == ".py":
            findings.extend(FileScan(p, text, major).run())
        else:
            seen: set = set()

            def add(line, rule, message, severity="error", _p=p, _seen=seen):
                if (line, rule, message) in _seen:
                    return
                _seen.add((line, rule, message))
                findings.append({"file": _rel(_p), "line": line, "rule": rule,
                                 "severity": severity, "message": message})

            scan_template_text(text, 1, major is not None and major >= 3, add)
    findings.sort(key=lambda f: (f["file"] or "", f["line"], f["rule"]))
    return findings, n


# ----------------------------------------------------------------------------
# DagBag + timetable preview (runs inside the Airflow environment)
# ----------------------------------------------------------------------------


def prepare_environment(paths: list[Path]) -> list[str]:
    """Isolate Airflow before it is imported. Returns temp dirs to clean up."""
    cleanup = []
    sys.dont_write_bytecode = True  # do not leave __pycache__ in the user's DAG folders
    if not os.environ.get("AIRFLOW_HOME"):
        home = tempfile.mkdtemp(prefix="airflow-check-home-")
        cleanup.append(home)
        os.environ["AIRFLOW_HOME"] = home
    db_dir = tempfile.mkdtemp(prefix="airflow-check-db-")
    cleanup.append(db_dir)
    sqlite = f"sqlite:///{os.path.join(db_dir, 'airflow.db')}"
    # Never touch a real metadata DB: both config keys (2.x [database], legacy [core]).
    os.environ["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"] = sqlite
    os.environ["AIRFLOW__CORE__SQL_ALCHEMY_CONN"] = sqlite
    os.environ["AIRFLOW__CORE__LOAD_EXAMPLES"] = "False"
    os.environ.setdefault("AIRFLOW__LOGGING__LOGGING_LEVEL", "WARNING")
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    first_dir = next((p if p.is_dir() else p.parent for p in paths), None)
    if first_dir is not None and not os.environ.get("AIRFLOW__CORE__DAGS_FOLDER"):
        os.environ["AIRFLOW__CORE__DAGS_FOLDER"] = str(first_dir.resolve())
    for extra in [os.getcwd()] + [str((p if p.is_dir() else p.parent).resolve()) for p in paths]:
        if extra not in sys.path:
            sys.path.insert(0, extra)
    return cleanup


def load_dagbags(paths: list[Path]):
    import airflow  # noqa: F401  (imported for its side effects / version)

    major = _major(airflow.__version__)
    if major and major >= 3:
        try:
            from airflow.dag_processing.dagbag import DagBag  # Airflow >= 3.2
        except ImportError:
            from airflow.models.dagbag import DagBag  # Airflow 3.0 / 3.1

        def make(folder):
            return DagBag(dag_folder=str(folder))  # examples off via AIRFLOW__CORE__LOAD_EXAMPLES
    else:
        from airflow.models import DagBag

        def make(folder):
            return DagBag(dag_folder=str(folder), include_examples=False)

    dags, import_errors, parse_warnings = {}, {}, []
    for p in paths:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            bag = make(p.resolve())
        for dag_id, dag in bag.dags.items():
            dags.setdefault(dag_id, dag)
        for f, err in bag.import_errors.items():
            import_errors[f] = err
        for w in caught:
            parse_warnings.append({"file": _rel(w.filename), "line": w.lineno,
                                   "category": w.category.__name__, "message": str(w.message)[:300]})
        for f, lines in (getattr(bag, "captured_warnings", None) or {}).items():
            for line in lines:
                m = re.match(r"^(.*?):(\d+): (?:[\w.]+\.)?(\w+): (.*)$", line, re.S)
                if m:
                    parse_warnings.append({"file": _rel(m.group(1)), "line": int(m.group(2)),
                                           "category": m.group(3), "message": m.group(4)[:300]})
                else:
                    parse_warnings.append({"file": _rel(f), "line": None, "category": "Warning",
                                           "message": line[:300]})
    return airflow.__version__, dags, import_errors, parse_warnings


def core_timetable(dag):
    """Scheduler-side timetable (3.x SDK timetables lack next_dagrun_info)."""
    try:
        from airflow.serialization.serialized_objects import coerce_to_core_timetable
    except ImportError:
        return dag.timetable
    try:
        return coerce_to_core_timetable(dag.timetable)
    except Exception:  # noqa: BLE001 - fall back to whatever the DAG carries
        return dag.timetable


def _to_aware(value, tz):
    import pendulum

    if isinstance(value, str):
        return pendulum.parse(value, tz=tz)
    if value.tzinfo is None:
        return pendulum.instance(value, tz=tz)
    return pendulum.instance(value)


def preview_runs(dag, n: int, start_from: str | None):
    """Next ``n`` scheduled runs from ``start_from`` (or start_date), catchup-style."""
    from airflow.timetables.base import TimeRestriction

    tt = core_timetable(dag)
    tz = getattr(dag, "timezone", None) or "UTC"
    start_date = getattr(dag, "start_date", None)
    earliest = None
    if start_from:
        earliest = _to_aware(start_from, tz)
        if start_date is not None and _to_aware(start_date, tz) > earliest:
            earliest = _to_aware(start_date, tz)
    elif start_date is not None:
        earliest = _to_aware(start_date, tz)
    end_date = getattr(dag, "end_date", None)
    latest = _to_aware(end_date, tz) if end_date is not None else None
    if not hasattr(tt, "next_dagrun_info"):
        return [], earliest, "timetable has no next_dagrun_info(); cannot preview runs"
    if earliest is None:
        return [], None, "no start_date and no --from: cannot preview runs"
    out, last = [], None
    restriction = TimeRestriction(earliest=earliest, latest=latest, catchup=True)
    for _ in range(n):
        info = tt.next_dagrun_info(last_automated_data_interval=last, restriction=restriction)
        if info is None:
            break
        di = info.data_interval
        out.append({
            "run_after": _iso(info.run_after),
            "logical_date": _iso(getattr(info, "logical_date", None)),
            "data_interval_start": _iso(di.start) if di else None,
            "data_interval_end": _iso(di.end) if di else None,
        })
        if di is None:
            break
        last = di
    return out, earliest, None


def count_catchup_runs(dag, earliest, now) -> int:
    from airflow.timetables.base import TimeRestriction

    tt = core_timetable(dag)
    restriction = TimeRestriction(earliest=earliest, latest=now, catchup=True)
    last, n = None, 0
    while n < CATCHUP_COUNT_CAP:
        info = tt.next_dagrun_info(last_automated_data_interval=last, restriction=restriction)
        if info is None or info.run_after > now or info.data_interval is None:
            break
        last, n = info.data_interval, n + 1
    return n


def describe_dag(dag, n_runs: int, start_from: str | None, major: int | None) -> dict:
    tt = getattr(dag, "timetable", None)
    tt_name = type(tt).__name__ if tt is not None else None
    sched = getattr(dag, "schedule", None) if (major or 0) >= 3 else getattr(
        dag, "schedule_interval", None)
    warns: list[str] = []
    info = {
        "dag_id": dag.dag_id,
        "file": _rel(getattr(dag, "fileloc", None)),
        "schedule": repr(sched) if sched is not None else None,
        "timetable": tt_name,
        "timetable_summary": getattr(tt, "summary", None),
        "catchup": getattr(dag, "catchup", None),
        "start_date": _iso(getattr(dag, "start_date", None)),
        "end_date": _iso(getattr(dag, "end_date", None)),
        "max_active_runs": getattr(dag, "max_active_runs", None),
        "tasks": len(getattr(dag, "tasks", []) or []),
        "next_runs": [],
        "warnings": warns,
    }
    schedulable = bool(getattr(tt, "can_be_scheduled", True)) and tt_name not in (
        "NullTimetable", "OnceTimetable", None) and "Asset" not in (tt_name or "") \
        and "Dataset" not in (tt_name or "")
    if schedulable:
        try:
            runs, earliest, note = preview_runs(dag, n_runs, start_from)
            info["next_runs"] = runs
            info["preview_from"] = _iso(earliest)
            if note:
                warns.append(note)
            elif not runs:
                warns.append("timetable produced no runs from preview_from (end_date passed?)")
        except Exception as exc:  # noqa: BLE001 - report, never crash the whole check
            warns.append(f"could not preview runs: {type(exc).__name__}: {str(exc)[:200]}")
    zero_width = all(r.get("data_interval_start") == r.get("data_interval_end")
                     for r in info.get("next_runs") or [{}])
    if tt_name in TRIGGER_TIMETABLES and zero_width:
        warns.append(
            f"{tt_name}: each run has data_interval_start == data_interval_end == logical_date == "
            "the time the run fires, so {{ ds }} is the day the run fires. That is right if the "
            "tasks process the day they run ('the run's date', 'that day's file'): keep it. If they "
            "should process an earlier period, derive it from dag_run.logical_date or "
            "dag_run.run_after in one helper (ds is undefined on 3.x manual runs); use "
            "CronDataIntervalTimetable / DeltaDataIntervalTimetable only when each run processes "
            "the interval that just ended. Check next_runs.")
    start = getattr(dag, "start_date", None)
    now = datetime.now(timezone.utc)
    if schedulable and start is None:
        warns.append("scheduled DAG has no start_date")
    elif start is not None:
        try:
            if abs((_to_aware(start, "UTC") - now).total_seconds()) < 3600:
                warns.append("start_date is within an hour of now: it is probably computed at parse "
                             "time (datetime.now()/days_ago); use a fixed date")
        except Exception:  # noqa: BLE001
            pass
    if schedulable and info["catchup"] and start is not None:
        try:
            import pendulum

            n = count_catchup_runs(dag, _to_aware(start, "UTC"), pendulum.now("UTC"))
            if n > 1:
                more = "+" if n >= CATCHUP_COUNT_CAP else ""
                warns.append(f"catchup=True: about {n}{more} runs between start_date and now will be "
                             "created when the DAG is unpaused")
        except Exception:  # noqa: BLE001
            pass
    if not info["tasks"]:
        warns.append("DAG has no tasks")
    for t in getattr(dag, "tasks", []) or []:
        if "Sensor" not in type(t).__name__ and "sensor" not in str(getattr(t, "task_type", "")).lower():
            continue
        mode = getattr(t, "mode", None)
        timeout = getattr(t, "timeout", None)
        secs = timeout.total_seconds() if hasattr(timeout, "total_seconds") else timeout
        if mode == "poke" and not getattr(t, "deferrable", False) and secs is not None \
                and float(secs) >= DEFAULT_SENSOR_TIMEOUT_S:
            warns.append(f"sensor {t.task_id} pokes with a {int(float(secs) // 3600)} h timeout: it "
                         "holds a worker slot the whole time; set timeout= and mode='reschedule' "
                         "or deferrable=True")
    del warns[MAX_WARNINGS_PER_DAG:]
    return info


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # exit 3 on usage errors, not argparse's 2
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        sys.exit(EXIT_USAGE)


def parse_args(argv):
    p = _Parser(
        prog="airflow_check.py",
        description="Parse DAG files with the installed Airflow, preview the next scheduled runs "
                    "of each DAG, and run version-aware static checks.",
        epilog="Exit codes: 0 clean, 1 import errors, 2 static findings (severity error), "
               "3 usage/environment error. Warnings never fail.",
    )
    p.add_argument("paths", nargs="*", metavar="DAGS_PATH",
                   help="DAG files or folders (default: $AIRFLOW__CORE__DAGS_FOLDER, else ./dags)")
    p.add_argument("--dag-id", action="append", default=[],
                   help="only report this DAG (repeatable)")
    p.add_argument("--runs", type=int, default=3, help=f"scheduled runs to preview per DAG "
                   f"(default 3, max {MAX_RUNS})")
    p.add_argument("--from", dest="start_from", metavar="DATE",
                   help="preview runs from this date/datetime (naive values use the DAG timezone); "
                        "default: the DAG start_date")
    p.add_argument("--json", action="store_true", help="print the full JSON result")
    p.add_argument("--static-only", action="store_true",
                   help="skip the DagBag parse and run preview; only run static rules")
    p.add_argument("--target-version", metavar="X.Y",
                   help="Airflow version the static rules target (default: installed version)")
    args = p.parse_args(argv)
    if args.runs < 0 or args.runs > MAX_RUNS:
        p.error(f"--runs must be between 0 and {MAX_RUNS}")
    if args.start_from:
        try:
            datetime.fromisoformat(args.start_from.replace("Z", "+00:00"))
        except ValueError:
            p.error(f"--from: not an ISO date/datetime: {args.start_from!r}")
    return args


def default_paths() -> list[Path]:
    env = os.environ.get("AIRFLOW__CORE__DAGS_FOLDER")
    if env:
        return [Path(env)]
    return [Path("dags")]


def build_result(args) -> tuple[dict, int]:
    paths = [Path(p) for p in args.paths] or default_paths()
    missing = [str(p) for p in paths if not p.exists()]
    result = {"airflow_version": None, "target_version": None, "paths": [str(p) for p in paths],
              "import_errors": [], "dags": [], "findings": [], "parse_warnings": [],
              "errors": [], "summary": {}}
    if missing:
        result["errors"].append(f"path not found: {', '.join(missing)}")
        return result, EXIT_USAGE

    installed = installed_airflow_version()
    target = args.target_version or installed
    result["airflow_version"] = installed
    result["target_version"] = target
    major = _major(target)
    env_error = False
    if major is None:
        result["errors"].append("Airflow version unknown: apache-airflow is not installed in this "
                                "interpreter and --target-version was not given; only "
                                "version-neutral static rules ran")
        env_error = not args.static_only

    findings, n_files = static_scan(paths, major)
    result["summary"]["files_scanned"] = n_files

    selected_files = None
    if not args.static_only and installed:
        cleanup = prepare_environment(paths)
        try:
            version, dags, import_errors, parse_warnings = load_dagbags(paths)
            result["airflow_version"] = version
            result["import_errors"] = [{"file": _rel(f), "error": _trim_error(e)}
                                       for f, e in sorted(import_errors.items())]
            scanned = {str(Path(p).resolve()) for p in iter_files(paths)}
            seen_w: set = set()
            for w in parse_warnings:
                key = (w.get("file"), w.get("line"), w.get("message"))
                if not w.get("file") or key in seen_w \
                        or str(Path(w["file"]).resolve()) not in scanned:
                    continue
                seen_w.add(key)
                result["parse_warnings"].append(w)
            del result["parse_warnings"][MAX_PARSE_WARNINGS:]
            wanted = set(args.dag_id)
            chosen = [d for i, d in sorted(dags.items()) if not wanted or i in wanted]
            if wanted:
                not_found = sorted(wanted - set(dags))
                if not_found:
                    result["errors"].append(f"dag_id not found: {', '.join(not_found)}")
                selected_files = {_rel(getattr(d, "fileloc", None)) for d in chosen}
            result["dags"] = [describe_dag(d, args.runs, args.start_from, _major(version))
                              for d in chosen[:MAX_DAGS]]
            if len(chosen) > MAX_DAGS:
                result["errors"].append(f"{len(chosen) - MAX_DAGS} more DAGs not shown")
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"DagBag load failed: {type(exc).__name__}: {str(exc)[:500]}")
            env_error = True
        finally:
            for d in cleanup:
                shutil.rmtree(d, ignore_errors=True)
    elif not args.static_only and not installed:
        env_error = True

    if selected_files is not None:
        findings = [f for f in findings if f["file"] in selected_files]
    total_findings = len(findings)
    result["findings"] = findings[:MAX_FINDINGS]
    n_err = sum(1 for f in findings if f["severity"] == "error")
    result["summary"].update({
        "dags": len(result["dags"]),
        "import_errors": len(result["import_errors"]),
        "findings_error": n_err,
        "findings_warning": total_findings - n_err,
        "findings_truncated": max(0, total_findings - MAX_FINDINGS),
    })
    if env_error:
        code = EXIT_USAGE
    elif result["import_errors"]:
        code = EXIT_IMPORT
    elif any(e.startswith("dag_id not found") for e in result["errors"]):
        code = EXIT_USAGE
    elif n_err:
        code = EXIT_FINDINGS
    else:
        code = EXIT_OK
    result["exit_code"] = code
    return result, code


def render_text(res: dict) -> str:
    out = []
    s = res.get("summary", {})
    out.append(f"Airflow {res.get('airflow_version') or '?'} (rules target "
               f"{res.get('target_version') or '?'}); files scanned: {s.get('files_scanned', 0)}")
    for e in res.get("errors", []):
        out.append(f"ERROR: {e}")
    ie = res.get("import_errors", [])
    if ie:
        out.append(f"\nIMPORT ERRORS ({len(ie)}):")
        for e in ie:
            last = e["error"].strip().splitlines()[-1] if e["error"].strip() else ""
            out.append(f"  {e['file']}: {last}")
    for d in res.get("dags", []):
        out.append(f"\nDAG {d['dag_id']}  ({d['file']})")
        out.append(f"  schedule={d['schedule']} timetable={d['timetable']} catchup={d['catchup']} "
                   f"start_date={d['start_date']} max_active_runs={d['max_active_runs']} "
                   f"tasks={d['tasks']}")
        for r in d.get("next_runs", []):
            out.append(f"  run_after={r['run_after']} logical_date={r['logical_date']} "
                       f"interval=[{r['data_interval_start']}, {r['data_interval_end']})")
        for w in d.get("warnings", []):
            out.append(f"  warning: {w}")
    fs = res.get("findings", [])
    if fs:
        out.append(f"\nFINDINGS ({s.get('findings_error', 0)} error, "
                   f"{s.get('findings_warning', 0)} warning):")
        for f in fs:
            out.append(f"  {f['file']}:{f['line']} [{f['severity']}] {f['rule']}: {f['message']}")
    out.append(f"\nexit {res.get('exit_code')}")
    return "\n".join(out)


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    # Airflow and DAG files print/log to stdout; keep stdout for our result only.
    sys.stdout.flush()
    real_fd = os.dup(1)
    os.dup2(2, 1)
    try:
        try:
            res, code = build_result(args)
        except Exception as exc:  # noqa: BLE001
            res = {"errors": [f"internal error: {type(exc).__name__}: {exc}"], "exit_code": EXIT_USAGE}
            code = EXIT_USAGE
        res["exit_code"] = code
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(real_fd, 1)
        os.close(real_fd)
    text = json.dumps(res, indent=2, default=str) if args.json else render_text(res)
    sys.stdout.write(text + "\n")
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    sys.exit(main())
