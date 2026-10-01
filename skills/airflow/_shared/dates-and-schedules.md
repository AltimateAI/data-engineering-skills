# Airflow dates and schedules: verified reference

Every statement below was checked by running probes against Airflow 3.3 and Airflow 2.11: timetable
`next_dagrun_info`, `airflow dags test`, `dag.test()`, a real scheduler (`airflow standalone`),
`airflow backfill create`, and CLI triggers. When this file says "3.x", read it as "Airflow >= 3.0 with
default config". The scheduler checks were run on 3.3 only.

## Contents
1. [Core rule](#1-core-rule)
2. [Schedule value -> timetable -> run dates](#2-schedule-value---timetable---run-dates)
3. [Recipes for processing the previous period](#3-recipes-for-processing-the-previous-period)
4. [Manual, asset-triggered and backfill runs](#4-manual-asset-triggered-and-backfill-runs)
5. [Removed context keys and why a rename is not enough](#5-removed-context-keys-and-why-a-rename-is-not-enough)
6. [catchup, start_date, max_active_runs, backfill, idempotency](#6-catchup-start_date-max_active_runs-backfill-idempotency)
7. [Testing date logic](#7-testing-date-logic)
8. [Decision table](#8-decision-table)

## 1. Core rule
The same schedule string gives different dates on 2.x and 3.x. Airflow 2 used **interval timetables**:
a run fires at the end of its period, and `logical_date`/`ds`/`data_interval_start` all mean "the period
being processed". Airflow 3 maps cron strings, presets and `timedelta` to **trigger timetables**: a run
fires at the tick, `logical_date == data_interval_start == data_interval_end == run_after`, and `ds` is
the day the run fires, not the previous day. On 3.x, manual and asset-triggered runs usually have no
logical date at all. So always find the version first. Then make the timetable explicit and work out
the processed period from what the run actually carries (section 3). Don't rename keys one by one.

## 2. Schedule value -> timetable -> run dates
Example: `start_date=2026-03-02 00:00 UTC`, daily at 04:00 UTC. Each row shows **the run that fires at
2026-03-03 04:00 UTC**.

| `schedule=` | 3.x timetable | 2.x timetable | logical_date / `ds` | data_interval_start -> end |
|---|---|---|---|---|
| `"0 4 * * *"` or `"@daily"` (00:00) | CronTriggerTimetable | CronDataIntervalTimetable | 3.x: 03-03 04:00 / `2026-03-03`. 2.x: 03-02 04:00 / `2026-03-02` | 3.x: 03-03 04:00 -> 03-03 04:00 (zero width). 2.x: 03-02 04:00 -> 03-03 04:00 |
| `timedelta(days=1)` | DeltaTriggerTimetable | DeltaDataIntervalTimetable | as above: 3.x is the fire time, 2.x is one period earlier | 3.x zero width, 2.x one day |
| `CronDataIntervalTimetable("0 4 * * *", timezone=tz)` | same on both | same | 03-02 04:00 / `2026-03-02` | 03-02 04:00 -> 03-03 04:00 |
| `CronTriggerTimetable("0 4 * * *", timezone=tz)` | same on both | same | 03-03 04:00 / `2026-03-03` | zero width at 03-03 04:00 |
| `CronTriggerTimetable(..., interval=timedelta(days=1))` | same on both | same | 03-02 04:00 (logical_date = interval start) | 03-02 04:00 -> 03-03 04:00 |
| `"@once"` / `None` | OnceTimetable / NullTimetable | same | one run at start_date / manual only | |

- Imports: on 3.2+ all four timetables come from `airflow.sdk`. On 2.x, 3.0 and 3.1 use
  `airflow.timetables.interval` (`CronDataIntervalTimetable`, `DeltaDataIntervalTimetable`) and
  `airflow.timetables.trigger` (`CronTriggerTimetable`, `DeltaTriggerTimetable`). Both 2.11 and 3.x ship
  all four.
- `run_after` is when a run becomes due. It is always the tick. For interval timetables it is
  `data_interval_end`.
- Config (`[scheduler]`) decides how strings and `timedelta` are mapped. It has no effect on explicit
  timetable objects:

  | key | 3.x default | 2.11 default |
  |---|---|---|
  | `create_cron_data_intervals` | False (cron and presets become trigger timetables) | True |
  | `create_delta_data_intervals` | False | True |
  | `catchup_by_default` | False | True |

  Setting `AIRFLOW__SCHEDULER__CREATE_CRON_DATA_INTERVALS=True` on 3.x brings back the 2.x mapping. It is
  read when the DAG file is parsed and depends on the deployment, so pass an explicit timetable in code
  instead.
- Timezone: a cron **string** uses the timezone of `start_date`. A timetable object uses its `timezone=`
  argument.
- On 3.x, a scheduled run's `run_id` is built from `run_after`, not from the logical date. An interval
  run with logical date 09-29 is named `scheduled__2026-09-30T04:00...`. Never parse dates out of
  `run_id`.

## 3. Recipes for processing the previous period
**Default (both versions, any timetable, any run type):** compute the window with a helper. Don't read
`ds` directly. The helper was checked for scheduled, backfill, `dags test`, manual runs without a logical
date, and `params` overrides, on both versions:

```python
import pendulum

def prev_day(d):
    return d.subtract(days=1)

def prev_business_day(d):              # Mon -> Fri; no holiday calendar
    d = d.subtract(days=1)
    while d.day_of_week in (pendulum.SATURDAY, pendulum.SUNDAY):
        d = d.subtract(days=1)
    return d

def run_window(dag_run, params=None, tz="UTC", prev=prev_day):
    """[start, end) of the period this run processes, tz-aware in the business timezone."""
    day = (params or {}).get("day")                       # explicit reprocess wins
    if day:
        start = pendulum.parse(day, tz=tz)
        return start, start.add(days=1)
    s, e = dag_run.data_interval_start, dag_run.data_interval_end
    if s is not None and e is not None and e > s:          # interval timetable: the run IS the period
        return pendulum.instance(s).in_tz(tz), pendulum.instance(e).in_tz(tz)
    anchor = dag_run.logical_date or dag_run.run_after     # trigger timetable / 3.x manual / asset
    start = prev(pendulum.instance(anchor).in_tz(tz).start_of("day"))
    return start, start.add(days=1)
```

`prev=` is applied only when the run carries no interval (trigger timetables, 3.x manual and asset
runs). Under an interval timetable the interval is returned as is, whatever `prev` is; for a run that
must process its own day, use a trigger timetable with `prev=lambda d: d`.

Use it in a task as `run_window(context["dag_run"], context["params"], "America/New_York")`. In
templates, register it with `user_defined_macros={"window_ds": lambda dr, p: run_window(dr, p)[0].to_date_string()}`
and write `{{ window_ds(dag_run, params) }}`. Declare `params={"day": Param(None, type=["null", "string"], format="date")}`.
Why each piece matters:
- `dag_run.*` datetimes are **stdlib `datetime`** on both versions. `.subtract()` and `.in_tz()` fail
  on them, so wrap them with `pendulum.instance()`. The context values `logical_date` and
  `data_interval_*` are pendulum objects, but on 3.x manual runs they are missing.
- Build day boundaries in the local timezone with `start_of("day")`, not as `anchor - 24h`. The New York
  day of 2026-03-08 is 23 hours long.
- The `ds`/`ts` context values are the **UTC** date. A 22:00 New York run gets `ds` = the next
  calendar day. The `| ds` filter only formats the datetime it is given, in that datetime's own
  timezone, so convert first: `{{ logical_date.in_timezone('America/New_York') | ds }}`.

| Need | Schedule | `prev=` | Checked result |
|---|---|---|---|
| Daily, previous calendar day, UTC | `CronTriggerTimetable("0 4 * * *", timezone="UTC")` | `prev_day` | backfill run 03-09 04:00 -> window 03-08 |
| Keep Airflow-2 meaning for existing `{{ ds }}` / `data_interval_*` code | `CronDataIntervalTimetable(cron, timezone=tz)` | helper uses the interval | run due 03-09 04:00 -> 03-08 on both versions |
| Weekdays 06:30 New York, previous business day | `CronTriggerTimetable("30 6 * * 1-5", timezone="America/New_York")` | `prev_business_day` | Monday 03-09 run -> Friday 03-06; the Thursday run -> Wednesday |
| Same, in interval style | `CronDataIntervalTimetable("30 6 * * 1-5", timezone=NY)` | `prev_business_day` (used for manual runs) | Monday run's interval is Fri 06:30 -> Mon 06:30 and includes the weekend; if the task processes one business day, use the local date of the window start, not the whole window |

DST (US clocks changed on 2026-03-08):
- A cron timetable with `timezone="America/New_York"` (or a cron string with a New York `start_date`)
  kept 06:30 local time on both sides of the change. In UTC the run moved from 11:30 to 10:30.
- A UTC cron `"30 11 * * 1-5"` drifted to **07:30** New York time after the change.
- `timedelta(days=1)` keeps an exact 24 h gap, so a run anchored at 06:30 became 07:30 local.
- Use a timezone-aware cron timetable for any "local business time" requirement. Don't shift a UTC cron
  by hand.

## 4. Manual, asset-triggered and backfill runs
Runs on 3.x (the rows marked "real scheduler" came from actual scheduler runs):

| Run | logical_date | data_interval_* | `ds`/`ts` in context and Jinja | `dag_run.run_after` |
|---|---|---|---|---|
| Scheduled, trigger timetable (real scheduler) | the tick | zero width at the tick | tick date | tick |
| Scheduled, interval timetable (real scheduler) | interval start | the interval | interval start date | interval end |
| Backfill (real scheduler) | same as a scheduled run for that tick | same | same | same as scheduled |
| Manual from UI/API/CLI **without** a logical date (the default) | **missing** (`dag_run.logical_date is None`) | **missing** | **missing**: `{{ ds }}` raises `UndefinedError`, and the task fails | time of the trigger |
| Asset-triggered (real scheduler) | **missing** | **missing** | **missing** | time the run was queued |
| Manual **with** logical date D | D | worked out from the **trigger time**, not from D. Under an interval timetable you get the latest finished interval before the trigger | D's date | time of the trigger |

What to use instead:
- The run's day is `dag_run.run_after` (as `logical_date or run_after`). The key is absent from the context, so
  `context.get("logical_date")` returns None. `datetime.now()` is wrong too, because a run cleared
  and re-run later computes a different day.
- To reprocess a specific day, pass `params` (`{"day": "2026-03-04"}`) or run a backfill. A manual run
  with logical date D under an interval timetable processes the interval before the *trigger time*.
  `dag_run.logical_date` is unique per DAG, so triggering on a date that a backfill or scheduled run
  already used fails with `UNIQUE constraint failed`.
- Pure-Jinja fallback that works on both versions (it relies on `or` short-circuiting on 2.x):
  `{{ ((dag_run.logical_date or dag_run.run_after) - macros.timedelta(days=1)) | ds }}`. It is correct
  only for trigger timetables, and only in UTC. Prefer the macro from section 3.
- On 2.x, manual runs always get a logical date (default: now), and their interval is the latest
  finished interval.

## 5. Removed context keys and why a rename is not enough
Keys present on 2.11 and missing on 3.3: `execution_date`, `next_execution_date`, `prev_execution_date`,
`prev_execution_date_success`, `next_ds(_nodash)`, `prev_ds(_nodash)`, `yesterday_ds(_nodash)`,
`tomorrow_ds(_nodash)`, `conf`, `test_mode`, `triggering_dataset_events`, `expanded_ti_count`.

| 2.x key | 3.x replacement | Semantic trap |
|---|---|---|
| `execution_date` | `logical_date` | The value matches only under interval timetables. Under 3.x default trigger timetables it is **one period later** for the same wall-clock run, so a plain rename shifts every output by one day. |
| `next_ds`, `next_execution_date` | `data_interval_end` | Equal to `logical_date` under trigger timetables, and missing on manual or asset runs. |
| `yesterday_ds`, `tomorrow_ds` | `run_window(...)`, or `macros.ds_add(ds, ±1)` | `ds` itself moved one day later under trigger timetables, so `ds_add(ds, -1)` on 3.x equals 2.x `ds`. Port by meaning (which period is processed), not by name. |
| `prev_ds`, `prev_execution_date` | the previous schedule tick, computed from the timetable | On 2.x this is the previous *schedule point* (the same date on manual runs), so `ds_add(ds, -1)` is right only for daily schedules: -7 for weekly, and hourly, monthly or weekday crons need the timetable. |
| `prev_execution_date_success` | `prev_data_interval_start_success` / `prev_start_date_success` | `prev_data_interval_*_success` are missing on manual runs without a logical date. `prev_start_date_success` is present (None on the first run). |
| `triggering_dataset_events` | `triggering_asset_events` | |
| `conf` | `from airflow.sdk import conf` | |

- **Silent failure:** a TaskFlow parameter named after a removed key (`def f(execution_date=None)`) raises
  no error on 3.x. It simply stays `None`. `ds` and `logical_date` are still injected. Search for these
  parameters. Don't wait for a crash.
- Removed keys in Jinja strings or in `get_current_context()[...]` are not import errors: the DAG file
  parses cleanly and fails only when the task runs. Grep for them, then run the DAG (section 7).

## 6. catchup, start_date, max_active_runs, backfill, idempotency
- **catchup** defaults to False on 3.x and True on 2.11. Always pass it explicitly. When moving a DAG
  that relied on catch-up, set `catchup=True`, or runs are silently lost.
- **First run after deploy with a past `start_date`**, same on both versions:
  - `catchup=False` runs only the latest finished period: the most recent past tick (trigger), the latest
    finished interval (interval), or **"now", unaligned** (`DeltaTriggerTimetable`).
  - `catchup=True` starts at the first tick at or after `start_date`. A trigger timetable runs *at*
    that tick. An interval timetable runs one period later.
- **start_date**: use a fixed, tz-aware value such as `pendulum.datetime(2026, 1, 1, tz="America/New_York")`.
  Its timezone is the cron timezone for string schedules. Never use `now()`.
- **max_active_runs** defaults to 16 (`[core] max_active_runs_per_dag`) on both versions. Catch-up runs
  start concurrently: three were observed starting within one second. Set `max_active_runs=1` when runs
  depend on each other's output. The backfill CLI has its own `--max-active-runs`.
- **Backfill on 3.x** runs through the scheduler and works even with `catchup=False`:
  `airflow backfill create --dag-id D --from-date 2026-03-05T00:00:00+00:00 --to-date 2026-03-10T23:59:00+00:00 [--reprocess-behavior none|failed|completed] [--dry-run]`.
  - The range is compared with **logical dates**, so pass full timestamps. A date-only `--to-date`
    means 00:00 and leaves out that day's tick.
  - Under interval timetables the logical date is the interval start.
  - `--dry-run` lists the logical dates without creating runs, so use it first.
  - Weekday crons skip weekends in a backfill.
  - On 2.x the command is `airflow dags backfill -s ... -e ...`.
- **Idempotency**: key every write on the run's window and replace that partition in one transaction:
  delete-then-insert, `MERGE`, or `INSERT OVERWRITE ... PARTITION`. Re-running the same run must leave
  the same rows.
  - Checked: two runs for 03-05 plus one for 03-06 gave exactly one row per day.
  - A version keyed on `now()` wrote today's date for all three runs and appended duplicates. Every
    backfill run would land on the day it ran.

## 7. Testing date logic
- `airflow dags test <dag> <D>` treats D as a **manual** logical date, and the interval is inferred from
  D:
  - Interval timetables: the interval that *ends* at or before D. With D = 03-05 00:00 and a 04:00 cron
    you get 03-03 04:00 -> 03-04 04:00.
  - Trigger timetables: zero width at D.
  - To reproduce a scheduled interval run, pass D = its `run_after` tick. The interval then matches, but
    `ds` will be D, not the interval start. This is another reason to read the window, not `ds`.
  - On 3.x, `dag_run.run_after` is the wall clock in `dags test`.
- `airflow dags test <dag>` with no date uses logical date = now on both versions. It does **not**
  reproduce a 3.x UI trigger. On 3.x, reproduce that with
  `dag.test(logical_date=None, run_after=pendulum.datetime(...))`.
- Timetable oracle (no DB, no scheduler) for "what does the scheduler do":
  ```python
  from airflow.timetables.base import TimeRestriction
  tt = dag.timetable          # 3.x: coerce_to_core_timetable(dag.timetable) from airflow.serialization.encoders
  info = tt.next_dagrun_info(last_automated_data_interval=None,
                             restriction=TimeRestriction(dag.start_date, None, True))
  info.logical_date, info.data_interval, info.run_after   # call again with last_automated_data_interval=info.data_interval
  ```
  Its results matched real scheduler runs on 3.3. Use it to check DST, weekends and the previous-period
  logic across a date range.

## 8. Decision table
| User says | Use |
|---|---|
| "process yesterday's data", daily, on 3.x | explicit `CronTriggerTimetable(cron, timezone=tz)` + `run_window(..., prev=prev_day)`. Don't use bare `{{ ds }}` |
| "migrate this 2.x DAG and keep behaviour" | explicit `CronDataIntervalTimetable` (or `DeltaDataIntervalTimetable`) + `catchup` set as it was (2.x default True). Manual runs: 2.x processed the latest *closed* cron interval before the trigger, which the core timetable's `infer_manual_data_interval(run_after=...)` reproduces; `run_window` gives the previous calendar day instead, so use it only when that is what manual runs should process |
| "run at 6:30 New York time on business days" | `CronTriggerTimetable("30 6 * * 1-5", timezone="America/New_York")`. Never a shifted UTC cron |
| "report on the previous business day" | the row above + `prev=prev_business_day` (add a holiday calendar if holidays matter) |
| "works on schedule but fails when triggered manually" | `logical_date`/`ds`/`data_interval_*` are missing. Use `dag_run.run_after` or `params` through `run_window` |
| "rerun / reprocess 2026-03-04" | `params={"day": "2026-03-04"}`, or `airflow backfill create` with `--reprocess-behavior`. Not a manual run with that logical date |
| "don't backfill history on deploy" | `catchup=False` (explicit). It still runs the latest finished period once |
| "load all missing days since start_date" | `catchup=True` + `max_active_runs` to cap parallelism, or a one-off `backfill create --dry-run`, then the real command |
| "triggered when upstream data lands" (assets) | there is no logical date. Take the day from `run_after` or from `triggering_asset_events`, never from `ds` |
| "safe to re-run" | overwrite the partition keyed on `run_window`, in one transaction. Never key on `now()`/`CURRENT_DATE` |
