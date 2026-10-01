# Airflow 2 -> 3 runtime traps: verified reference

Everything here imports cleanly on 3.x and passes a single `airflow dags test`, then
writes different data (or fails) on the 3rd run, on a manual trigger or on an
asset-triggered run. Every row was checked by replaying the same runs against one
metadata DB on Airflow **2.11.2** and **3.3.2** (scheduled runs with the scheduler's
dates, CLI triggers without a logical date, scheduler-style asset-triggered runs).

## Contents
1. [State carried between runs](#1-state-carried-between-runs)
2. [Datasets -> Assets, aliases and event accessors](#2-datasets---assets-aliases-and-event-accessors)
3. [Asset-triggered runs have no data interval](#3-asset-triggered-runs-have-no-data-interval)
4. [CLI / API / UI triggers without a logical date](#4-cli--api--ui-triggers-without-a-logical-date)
5. [Template files (.sh, .sql, .j2)](#5-template-files-sh-sql-j2)
6. [Removed date keys: 2.x values by cadence](#6-removed-date-keys-2x-values-by-cadence)
7. [Plugins: macros, timetables, operators, hooks](#7-plugins-macros-timetables-operators-hooks)

## 1. State carried between runs

**Same-DAG XCom from earlier runs.** `ti.xcom_pull(task_ids=T, key=K, include_prior_dates=True)`:

| run | 2.11 | 3.3 |
|---|---|---|
| 1st | `None` | `None` |
| 2nd | previous value | previous value (only one exists, so a scalar) |
| 3rd and later | latest previous value | **a list of every previous value, in no guaranteed date order** |

Without `map_indexes`, 3.x fetches all matching XComs (ordered only by `map_index`,
not by date) and only unwraps a single hit. So a comparison like `previous == current`
is silently False from the 3rd run on (a "changed / unchanged" flag flips, a watermark
reloads everything), and `prev[-1]` can pick a stale value. Fix, checked on 2.11 and
3.3 to return the latest earlier value:
```python
prev = ti.xcom_pull(task_ids="t", key="k", include_prior_dates=True, map_indexes=-1)
```
If the current run already pushed this key (a retry clears it first), that value counts
as the latest.
A one- or two-run test cannot show this. Replay at least 3 consecutive runs against
one metadata DB.

**Cross-DAG XCom.** `ti.xcom_pull(dag_id="other", task_ids=..., include_prior_dates=True)`
returned the other DAG's latest value with a logical date at or before this run's on
2.11. On 3.3 the pull is matched on *this* run's `run_id`, so it returns **`None`**
unless the other DAG happens to have a run with the same id (two DAGs on the same
schedule can). Replace it with one of:
- **An explicit `run_id=`** of the other DAG's run, when you know which run it is.
- **Read what the other DAG produced**: e.g. the latest output partition/file/row
  dated at or before this run's date. This keeps the "at or before" meaning, also
  for backfills and re-runs.
- **Asset events**: the producer sets `outlet_events[asset].extra = {...}`; the
  consumer task declares `inlets=[asset]` and reads `inlet_events[asset]` (oldest
  first, checked on 3.3 and 2.11). It contains every event, including ones newer than
  the run being re-processed, so filter by the date in `extra`, don't just take `[-1]`.
- The Airflow REST API (needs credentials on the worker; the heaviest option).

**Metadata-DB queries in task code** (`create_session`, `@provide_session`,
`settings.Session`, `DagRun.find`, `session.query(DagRun|TaskInstance|XCom)`) raise
`RuntimeError: Direct database access via the ORM is not allowed in Airflow 3.0` on a
3.x worker. In-process `dag.test()` / `airflow dags test` does **not** enforce this
(checked: the same query succeeded there), so a green `dags test` proves nothing;
grep for them.

| 2.x DB read | 3.x replacement (checked on 3.3) |
|---|---|
| previous run of this DAG (`DagRun.find`, query ordered by date) | `ti.get_previous_dagrun(state="success")` -> `.logical_date`, `.data_interval_start`, `.run_id`; or context `prev_start_date_success`, `prev_data_interval_start_success` (None on the first run) |
| cursor / watermark / fingerprint stored in XCom or a DB table | same-DAG XCom with `include_prior_dates=True, map_indexes=-1` (above), or your own state file/table keyed by DAG and period |
| Variable as a counter/cursor | `Variable.set(k, v)` needs a **str** on 3.x unless `serialize_json=True` (an int raises a pydantic `ValidationError`; 2.11 stored `'5'`); use `str()` / `json.dumps` / `serialize_json=True` and parse on read. `Variable.get(k, default=...)` on 3.x: `default_var=` raises `TypeError` (and 2.11 accepts only `default_var`) |
| another DAG's latest value | see cross-DAG XCom above |

## 2. Datasets -> Assets, aliases and event accessors
- `airflow.datasets.Dataset` / `DatasetAlias` -> `airflow.sdk.Asset` / `AssetAlias`;
  the context key and parameter `triggering_dataset_events` -> `triggering_asset_events`.
  ruff (AIR3) flags the imports, but not the parameter name, a
  `context["triggering_dataset_events"]` lookup, or URI-string keys (checked, ruff 0.16).
- **Keys are objects, not URI strings.** On 3.3 `outlet_events["s3://..."]` and
  `triggering_asset_events["s3://..."]` raise
  `TypeError: Key should be either an asset or an asset alias, not <class 'str'>`.
  2.11 accepted `outlet_events[ds.uri]` and keyed `triggering_dataset_events` by URI.
  Use `outlet_events[asset]`, `triggering_asset_events[asset]`,
  `triggering_asset_events.get(asset, [])`, and `event.asset.uri` for the URI.
  Custom operators in `plugins/` that do `context["outlet_events"][d.uri]` break the same way.
- **Alias events are listed more than once on 3.x.** Each event attached through an
  alias appears under its concrete `Asset` key **and** under every source
  `AssetAlias` key (1 + number of aliases entries), whatever the consumer is
  scheduled on (checked: 3 events through one alias -> 3 under the asset keys + the
  same 3 under the alias). 2.11 listed each once, under its dataset URI. A 2.x loop
  `for uri, events in triggering_dataset_events.items(): total += ...` therefore
  double-counts on 3.x. Read each event once, through the alias:
  ```python
  for ev in triggering_asset_events[MY_ALIAS]:      # each event exactly once
      key = ev.asset.uri                             # the concrete asset it was attached to
      n = ev.extra.get("rows", 0)
  ```
  Events emitted without an alias appear once, under their asset key. When iterating
  `.items()`, skip `AssetAlias` keys (or de-duplicate events) so nothing counts twice.
- Producers keep `outlet_events[MY_ALIAS].add(Asset(uri), extra={...})`; that API
  is unchanged.

## 3. Asset-triggered runs have no data interval
| | 2.11 dataset-triggered run | 3.3 asset-triggered run |
|---|---|---|
| `logical_date` / `ds` | time the run was created / its date | **missing** (`ds` -> UndefinedError) |
| `data_interval_start` -> `end` | earliest start -> latest end of the **source runs'** intervals of all consumed events | **missing** (None) |
| `dag_run.run_after` | n/a | time the run was queued |

Checked: hourly producers whose events came from runs 00:00-01:00, 01:00-02:00 and
01:00-02:00 gave the 2.11 consumer the interval 00:00 -> 02:00; 3.3 gave None. A
consumer that filters by `data_interval_*` processes nothing (or crashes) on 3.x.
Rebuild the same window from the events (fields checked on 3.3):
```python
def triggered_window(triggering_asset_events):
    """2.x data interval of an asset-triggered run: min source start .. max source end."""
    starts, ends = [], []
    for events in triggering_asset_events.values():   # duplicates (aliases) don't change min/max
        for ev in events:
            run = ev.source_dag_run
            if run is not None and run.data_interval_start is not None:
                starts.append(pendulum.instance(run.data_interval_start))
                ends.append(pendulum.instance(run.data_interval_end))
            else:                                       # event not produced by a DAG run
                starts.append(pendulum.instance(ev.timestamp))
                ends.append(pendulum.instance(ev.timestamp))
    return min(starts), max(ends)
```
Under an AND condition (`a & b`) the events of every asset count. When the source
DAG used a 3.x *trigger* timetable its runs have zero-width intervals; give the
source DAG an interval timetable (the default migration choice) so this matches 2.x.

## 4. CLI / API / UI triggers without a logical date
What a task saw on each version for a plain `airflow dags trigger <dag>` at time T
(daily `CronDataIntervalTimetable("30 2 * * *")`, checked):

| | 2.11 | 3.3 |
|---|---|---|
| `logical_date` | T | **None** (`dag_run.logical_date is None`) |
| `ds` | T's date | **undefined** |
| `data_interval_*` | latest *closed* interval before T: T = 03-05 01:15 -> 03-03 02:30..03-04 02:30; T = 03-05 09:15 -> 03-04 02:30..03-05 02:30 | **None** |
| `prev_ds`, `next_ds` | both = T's date | removed |
| `dag_run.run_after` | n/a | T |
| `dag_run.conf` / `params` | conf, merged into params | same (`--conf '{"day": ...}'` reached both) |

Port by what the old code read (read the runbook/README for how ops trigger it):
- it read `ds` / `logical_date` / `ts` (meaning "today" / "now"):
  `pendulum.instance(dag_run.logical_date or dag_run.run_after)`; in Jinja
  `{{ (dag_run.logical_date or dag_run.run_after) | ds }}` (or `| ts`). Checked on both.
- it read `data_interval_*` (meaning "the latest closed period"): the 3.x
  `airflow.sdk` timetable objects have **no** `infer_manual_data_interval`
  (AttributeError on 3.3); the core class does and returns exactly the 2.11 values above:
  ```python
  from airflow.timetables.interval import CronDataIntervalTimetable as CoreCron
  CRON = "30 2 * * *"                       # one constant for schedule= and this helper
  def manual_interval(dag_run, tz="UTC"):
      iv = CoreCron(CRON, timezone=tz).infer_manual_data_interval(
          run_after=pendulum.instance(dag_run.run_after))
      return iv.start, iv.end
  start = data_interval_start or manual_interval(dag_run)[0]   # scheduled runs keep theirs
  ```
- **Jinja trap:** `{{ logical_date or dag_run.run_after }}` still raises
  `UndefinedError` on such a run (missing keys are strict-undefined; `or` does not
  rescue them). Use `dag_run.logical_date` (an attribute that is None) or
  `{% if ds is defined %}`. Checked on 3.3.
- Reproduce such a run with `scripts/manual_run.py <dag> --run-after T [--conf JSON]`;
  `airflow dags test <dag> <date>` sets a logical date and is not the same run.

## 5. Template files (.sh, .sql, .j2)
Templates referenced by `bash_command="x.sh"` / `sql="x.sql"` are rendered with the
same context, so removed keys fail only when that task renders. Grep them too.
- `{{ conf.get(section, key) }}`: `conf` is gone from the 3.3 template context
  (UndefinedError). Put it back explicitly on the DAG:
  `from airflow.sdk import conf` (3.2+) and `user_defined_macros={"conf": conf}`;
  checked: the same template renders on 3.3. Custom `[section] key` options keep
  working through `AIRFLOW__SECTION__KEY`.
- `{{ tomorrow_ds }}`, `{{ yesterday_ds }}`, `{{ prev_ds }}`, `{{ next_ds }}`,
  `{{ execution_date }}`: UndefinedError on 3.3; replacements in section 6.
- One template for scheduled and manual runs, keeping 2.x meaning (scheduled: the
  interval's `ds`; manual trigger: the trigger date):
  ```jinja
  {%- set day = ds if ds is defined else (dag_run.run_after | ds) %}
  {%- set next_day = macros.ds_add(day, 1) %}
  ```
  `ds is defined` is False on a 3.3 manual run and True on scheduled runs (checked).

## 6. Removed date keys: 2.x values by cadence
2.11, interval timetables (the 2.x default), scheduled runs, checked:

| schedule | run's interval | `ds` | `yesterday_ds` | `tomorrow_ds` | `prev_ds` | `next_ds` |
|---|---|---|---|---|---|---|
| `@hourly` | 03-04 00:00-01:00 | 03-04 | 03-03 | 03-05 | 03-03 (previous hour's date) | 03-04 |
| daily | D | D | D-1 | D+1 | D-1 | D+1 |
| `0 6 * * 1` weekly | Mon 03-02 -> 03-09 | 03-02 | 03-01 | 03-03 | 02-23 | 03-09 |
| `0 6 * * 1-5` (Fri run) | Fri 03-06 -> Mon 03-09 | 03-06 | 03-05 | 03-07 (Sat) | 03-05 | 03-09 |
| `0 6 * * 1-5` (Mon run) | Mon 03-09 -> 03-10 | 03-09 | 03-08 (Sun) | 03-10 | 03-06 (Fri) | 03-10 |
| `0 0 1 * *` monthly | 03-01 -> 04-01 | 03-01 | 02-28 | 03-02 | 02-01 | 04-01 |
| manual trigger at T | latest closed | T | T-1 | T+1 | T | T |

With the schedule kept as an interval timetable on 3.x (so `ds` is unchanged):
- `yesterday_ds` / `tomorrow_ds` are always **calendar** ±1 day of `ds`, whatever the
  cadence: `macros.ds_add(ds, -1)` / `macros.ds_add(ds, 1)`.
- `next_ds` is the interval end's date: `data_interval_end | ds`.
- `prev_ds` is the **previous schedule tick**, not the previous day: -1 day for
  daily, -7 for weekly, previous month for monthly, Friday for a Monday weekday run.
  `prev_data_interval_start_success` equals it only when the previous run exists and
  succeeded (None on the first run). For irregular crons compute it from the cron
  (`croniter` is installed with Airflow 2.11 and 3.3; checked to give the 2.11
  `prev_ds` for every row above): `croniter(CRON, data_interval_start).get_prev(datetime)`.
- On a manual trigger all of them were relative to the trigger date (last row); keep
  that with `day` from section 5.
- If the schedule became a 3.x trigger timetable instead, `ds` itself moved one
  period later; see `dates-and-schedules.md` section 5.

## 7. Plugins: macros, timetables, operators, hooks
Pass `plugins/` (and any shared package) to ruff and the checker; they don't scan it
unless named, and the 3.x deployment needs the same `plugins_folder` on the
DAG processor and the workers.
- **Macros** registered with `AirflowPlugin.macros = [fn]` still render on 3.3 as
  `{{ macros.<plugin name>.<fn>(...) }}` (checked). Keep the plugin; don't inline.
- **Custom timetables**: a subclass of `airflow.timetables.base.Timetable`
  registered in a plugin's `timetables = [...]` still parses, serializes and runs on
  3.3 (checked). Keep the registration; the class must be importable where DAGs are parsed.
- **Operators / hooks**: `airflow.models.BaseOperator` still imports on 3.3 (it is
  re-exported from `airflow.sdk`) and ruff does not flag it; `airflow.hooks.base.BaseHook`
  is flagged (moved). Switch both to `from airflow.sdk import BaseOperator, BaseHook`.
  Inside `execute()`, fix `context["outlet_events"][x.uri]` -> `[x]` (section 2) and
  removed context keys (`context["execution_date"]` and the rest of section 6 are absent on 3.x).
