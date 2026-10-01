"""`airflow dags test` with the production triggerer/scheduler behaviours it skips (Airflow 3.3.2).

Usage: python defer_runner.py dags test <dag_id> <logical_date>

Plain `dags test` runs each trigger inline until its first event. That matches production
for the happy path (the trigger is rebuilt from ``serialize()``'s classpath + kwargs and the
task resumes in a fresh operator instance), but skips things a real deployment does. This
wrapper replaces ``airflow.sdk.definitions.dag._run_task`` with a copy that adds them, each
modelled on airflow/jobs/triggerer_job_runner.py, models/trigger.py and the scheduler:

* **Deferral timeouts.** ``defer(timeout=...)`` is enforced like the scheduler's
  ``check_trigger_timeouts``: once it passes (plus ``EVAL_DEFER_TIMEOUT_GRACE_S``, standing in
  for the scheduler's 15 s check interval) the trigger is cancelled (no ``on_kill``) and the
  task resumes with ``next_method="__fail__"``, ``error=TRIGGER_TIMEOUT``.
* **Triggerer restarts** (``EVAL_RESTART_AFTER_S``): after that many seconds the running trigger
  is cancelled without a message (the shutdown path: no ``on_kill``), ``cleanup()`` is awaited,
  and a new instance is built from the classpath + kwargs stored at deferral time.
* **User action** (``EVAL_USER_KILL_AFTER_S``): after that many seconds the task instance is
  marked failed in the metadata DB (what "mark failed" in the UI does), the trigger task is
  cancelled with the triggerer's user-action message, ``on_kill()`` is awaited (30 s bound),
  then ``cleanup()``. The task does not resume.
* **A trigger that raises or ends without an event** fails the task with
  ``error=TRIGGER_FAILURE``, as the triggerer does.
* **Task-end events.** A ``TaskSuccessEvent``/``TaskFailedEvent``/``TaskSkippedEvent`` from the
  trigger is applied with the production handler (``models.trigger.handle_event_submit``):
  the task instance gets its final state and XComs without resuming on a worker.
* **Event + defer kwargs.** The resume method gets ``defer(kwargs=...)`` merged with
  ``event=<payload>`` as in production; plain ``dags test`` drops the defer kwargs.
* The trigger's ``task_instance`` is set (dag_id, task_id, run_id, map_index, try_number) and
  the task instance stays ``deferred`` in the DB while the trigger runs, as in production.

It also measures event-loop stalls while triggers run (a 20 ms ticker; gaps over
``STALL_RECORD_S`` are recorded) and writes JSONL records to ``EVAL_DEFER_LOG``.
A trigger still running after ``EVAL_TRIGGER_HARD_CAP_S`` is cancelled and recorded as a hang.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
import traceback
from uuid import UUID

LOG_PATH = os.environ.get("EVAL_DEFER_LOG")
RESTART_AFTER_S = float(os.environ.get("EVAL_RESTART_AFTER_S") or 0)
USER_KILL_AFTER_S = float(os.environ.get("EVAL_USER_KILL_AFTER_S") or 0)
GRACE_S = float(os.environ.get("EVAL_DEFER_TIMEOUT_GRACE_S") or 4)
HARD_CAP_S = float(os.environ.get("EVAL_TRIGGER_HARD_CAP_S") or 120)
ON_KILL_TIMEOUT_S = 30
USER_ACTION_CANCEL_MSG = "__airflow_user_action__"  # triggerer_job_runner._USER_ACTION_CANCEL_MSG
STALL_RECORD_S = 0.15
TICK_S = 0.02


def record(**rec) -> None:
    rec["t"] = time.time()
    if LOG_PATH:
        with open(LOG_PATH, "a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")


def _drive_trigger(msg, task_sdk_ti, label: dict, mark_failed):
    """Run the deferred trigger like a triggerer would.

    Returns (next_method, next_kwargs), or None when a user action ended the task.
    """
    import psutil
    import structlog

    from airflow.sdk._shared.module_loading import import_string
    from airflow.sdk.bases.operator import TRIGGER_FAIL_REPR, TriggerFailureReason
    from airflow.sdk.execution_time.supervisor import (
        InProcessSupervisorComms,
        InProcessTestSupervisor,
        set_supervisor_comms,
    )
    from airflow.sdk.serde import deserialize, serialize

    timeout_s = msg.trigger_timeout.total_seconds() if msg.trigger_timeout is not None else None
    deferred_at = time.time()
    fail_at = deferred_at + timeout_s + GRACE_S if timeout_s is not None else None

    def build():
        trig = import_string(msg.classpath)(**deserialize(msg.trigger_kwargs))
        with contextlib.suppress(Exception):
            trig.task_instance = task_sdk_ti
        return trig

    async def first_event(trig):
        return await anext(trig.run(), None)

    async def stop(task, trig, message=None):
        task.cancel(message) if message else task.cancel()
        with contextlib.suppress(BaseException):
            await task

    async def main():
        loop = asyncio.get_running_loop()
        stalls: list[float] = []

        async def monitor():
            last = loop.time()
            while True:
                await asyncio.sleep(TICK_S)
                now = loop.time()
                gap = now - last - TICK_S
                if gap > STALL_RECORD_S:
                    stalls.append(round(gap, 3))
                last = now

        mon = asyncio.create_task(monitor())
        trig = build()
        task = asyncio.create_task(first_event(trig))
        outcome: tuple[str, object] = ("hang", None)
        try:
            if RESTART_AFTER_S:
                done, _ = await asyncio.wait({task}, timeout=RESTART_AFTER_S)
                if task not in done:
                    await stop(task, trig)
                    with contextlib.suppress(Exception):
                        await trig.cleanup()
                    record(kind="restart", **label)
                    trig = build()
                    task = asyncio.create_task(first_event(trig))
            limit = HARD_CAP_S
            if fail_at is not None:
                limit = min(limit, max(0.0, fail_at - time.time()))
            user_kill = bool(USER_KILL_AFTER_S) and USER_KILL_AFTER_S < limit
            done, _ = await asyncio.wait({task}, timeout=USER_KILL_AFTER_S if user_kill else limit)
            if task in done:
                try:
                    outcome = ("event", task.result())
                except BaseException as exc:  # noqa: BLE001 - mirrors the triggerer
                    outcome = ("error", "".join(traceback.format_exception(exc)))
            elif user_kill:
                mark_failed()
                record(kind="user_kill", **label)
                await stop(task, trig, USER_ACTION_CANCEL_MSG)
                try:
                    await asyncio.wait_for(trig.on_kill(), timeout=ON_KILL_TIMEOUT_S)
                except Exception as exc:  # noqa: BLE001 - the triggerer only logs these
                    record(kind="on_kill_error", error=repr(exc), **label)
                outcome = ("user_kill", None)
            else:
                await stop(task, trig)
                outcome = ("timeout", None) if fail_at is not None and time.time() >= fail_at - 0.05 else ("hang", None)
        finally:
            with contextlib.suppress(Exception):
                await trig.cleanup()
            mon.cancel()
        return outcome, stalls

    supervisor = InProcessTestSupervisor(
        id=task_sdk_ti.id,
        pid=os.getpid(),
        process=psutil.Process(),
        process_log=structlog.get_logger(logger_name="task").bind(),
        client=InProcessTestSupervisor._api_client(),
    )
    supervisor.comms = InProcessSupervisorComms(supervisor=supervisor)
    with set_supervisor_comms(supervisor.comms):
        (kind, value), stalls = asyncio.run(main())

    rec = dict(kind="trigger_" + kind, waited_s=round(time.time() - deferred_at, 3), stalls=stalls, **label)
    if kind == "user_kill":
        record(**rec)
        return None
    if kind == "event":
        if value is None:
            rec["kind"] = "trigger_no_event"
            record(**rec)
            return TRIGGER_FAIL_REPR, {"error": TriggerFailureReason.TRIGGER_FAILURE,
                                       "traceback": ["trigger exited without yielding an event"]}
        rec["payload"] = value.payload
        rec["event_type"] = type(value).__name__
        record(**rec)
        from airflow.triggers.base import BaseTaskEndEvent

        if isinstance(value, BaseTaskEndEvent):
            return ("end_event", value)
        # Production (models/trigger.py handle_event_submit) merges the event into the defer
        # kwargs; plain `dags test` 3.3.2 replaces them with {"event": ...}.
        next_kwargs = dict(deserialize(msg.next_kwargs) or {}) if msg.next_kwargs else {}
        next_kwargs["event"] = value.payload
        return msg.next_method, serialize(next_kwargs)
    if kind == "error":
        rec["traceback"] = value
        record(**rec)
        return TRIGGER_FAIL_REPR, {"error": TriggerFailureReason.TRIGGER_FAILURE, "traceback": str(value).splitlines()}
    record(**rec)
    if kind == "timeout":
        return TRIGGER_FAIL_REPR, {"error": TriggerFailureReason.TRIGGER_TIMEOUT}
    return TRIGGER_FAIL_REPR, {"error": TriggerFailureReason.TRIGGER_FAILURE,
                               "traceback": [f"eval: trigger did not fire within {HARD_CAP_S}s"]}


def _run_task(*, ti, task, run_triggerer: bool = False):
    """Copy of airflow.sdk.definitions.dag._run_task (3.3.2) with the inline trigger replaced."""
    import airflow.sdk.definitions.dag as dagmod
    from airflow.sdk.api.datamodels._generated import TaskInstance as TaskInstanceSDK
    from airflow.sdk.execution_time.comms import DeferTask
    from airflow.sdk.execution_time.supervisor import run_task_in_process
    from airflow.serialization.serialized_objects import create_scheduler_operator
    from airflow.utils.session import create_session
    from airflow.utils.state import TaskInstanceState

    log = dagmod.log
    taskrun_result = None
    log.info("[DAG TEST] starting task_id=%s map_index=%s", ti.task_id, ti.map_index)
    while True:
        try:
            ti.set_state(TaskInstanceState.QUEUED)
            task_sdk_ti = TaskInstanceSDK(
                id=UUID(str(ti.id)),
                task_id=ti.task_id,
                dag_id=ti.dag_id,
                run_id=ti.run_id,
                try_number=ti.try_number,
                map_index=ti.map_index,
                dag_version_id=UUID(str(ti.dag_version_id)),
            )
            record(kind="worker_run", task_id=ti.task_id, map_index=ti.map_index, try_number=ti.try_number,
                   run_id=ti.run_id)
            taskrun_result = run_task_in_process(ti=task_sdk_ti, task=task)
            msg = taskrun_result.msg
            ti.set_state(taskrun_result.ti.state)
            ti.task = create_scheduler_operator(taskrun_result.ti.task)
            label = {"task_id": ti.task_id, "map_index": ti.map_index, "try_number": ti.try_number,
                     "run_id": ti.run_id}
            if ti.state == TaskInstanceState.DEFERRED and isinstance(msg, DeferTask) and run_triggerer:
                record(kind="defer", classpath=msg.classpath, trigger_kwargs=msg.trigger_kwargs,
                       timeout_s=msg.trigger_timeout.total_seconds() if msg.trigger_timeout else None,
                       next_method=msg.next_method, next_kwargs=msg.next_kwargs, **label)
                resumed = _drive_trigger(msg, task_sdk_ti, label,
                                         mark_failed=lambda: ti.set_state(TaskInstanceState.FAILED))
                if resumed is None:
                    ti.set_state(TaskInstanceState.FAILED)
                    record(kind="task_end", state=str(ti.state), **label)
                    break
                if resumed[0] == "end_event":
                    # The trigger ended the task itself (TaskSuccessEvent & co): apply it with the
                    # production handler (models/trigger.py), no resume on a worker.
                    from airflow.models.taskinstance import TaskInstance as TIModel
                    from airflow.models.trigger import handle_event_submit

                    with create_session() as session:
                        db_ti = session.get(TIModel, ti.id)
                        handle_event_submit(resumed[1], task_instance=db_ti, session=session)
                        final_state = db_ti.state
                    ti.refresh_from_db()
                    record(kind="task_end", state=str(final_state), via="trigger_end_event", **label)
                    if final_state == TaskInstanceState.UP_FOR_RETRY:
                        taskrun_result = None
                    break
                ti.set_state(TaskInstanceState.QUEUED)
                ti.next_method, ti.next_kwargs = resumed
                with create_session() as session:
                    ti.state = TaskInstanceState.SCHEDULED
                    session.add(ti)
                continue
            record(kind="task_end", state=str(ti.state), **label)
            break
        except Exception:
            log.exception("[DAG TEST] Error running task %s", ti)
            record(kind="harness_exception", traceback=traceback.format_exc())
            if ti.state not in dagmod.FINISHED_STATES:
                ti.set_state(TaskInstanceState.FAILED)
                taskrun_result = None
                break
            raise
    log.info("[DAG TEST] end task task_id=%s map_index=%s", ti.task_id, ti.map_index)
    return taskrun_result


def main() -> None:
    import airflow.sdk.definitions.dag as dagmod

    dagmod._run_task = _run_task
    from airflow.__main__ import main as airflow_main

    sys.argv = ["airflow", *sys.argv[1:]]
    airflow_main()


if __name__ == "__main__":
    main()
