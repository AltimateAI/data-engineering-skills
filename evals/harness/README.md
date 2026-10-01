# Airflow skill eval harness

Measures whether the Airflow skills in `skills/airflow/` make an agent
(altimate-code, or Claude Code with `--runner claude-code`) produce working
Airflow code. Two arms run the same cases:

- **baseline**: the existing repo skills (dbt, snowflake, databricks,
  altimate-code) plus altimate-code's built-ins.
- **skill**: the same, plus `skills/airflow/*`.

Graders never trust what the agent says. They run the code: DagBag import,
`airflow dags test`, output data, timetable probes, re-runs, and pytest against
planted bugs.

## Files

| File | Purpose |
|---|---|
| `setup_envs.sh` | Creates the pinned Airflow venvs: grader envs and separate agent envs |
| `run_eval.py` | CLI: agent runs, grading, failure accounting, budget, self-test |
| `grading.py` | Helpers for case graders (stdlib only), plus cost accounting and the per-model price table |
| `isolation.py` | sandbox-exec profile (file and signal rules), contamination scan, broad-kill detection, agent-venv fingerprint and restore |
| `claude_code.py` | Claude Code runner: per-attempt config dir, skill staging, env, command, inventory check, stream monitor, usage-limit gate |
| `sanitize.py` | Replaces local paths in result artifacts; CLI for existing result dirs |
| `report.py` | Aggregates result dirs into `results.json` and `REPORT.md`; per-model paired deltas bootstrap over cases, pooled (all-model) deltas bootstrap over cases carrying all their models |
| `rescore_contamination.py` | Runs the contamination scan retroactively on stored `events.jsonl` of older campaigns; writes per-attempt flags and evidence, plus pass-rate reports with and without flagged runs |
| `run_triggers.py` | Trigger evals: which skill fires for each query in `evals/airflow/triggers/queries.json` |
| `../../tests/evals/` | Unit tests for the harness, plus integration tests against both envs |

## Setup

```bash
evals/harness/setup_envs.sh          # all four envs; or: setup_envs.sh 3.3 / 2.11
```

| Case `airflow_version` | grader venv (`${EVAL_ENV_ROOT:-~/.cache/des-evals}`) | agent venv | Contents |
|---|---|---|---|
| `"3.3"` | `airflow-3.3` | `agent-airflow-3.3` | apache-airflow 3.3.2, Python 3.12, official constraints |
| `"2.11"` | `airflow-2.11` | `agent-airflow-2.11` | apache-airflow 2.11.2, Python 3.12, official constraints |

All venvs also have duckdb and pandas (constrained), plus pytest and ruff>=0.13
(unconstrained). Agent venvs also have pip. Graders only ever use the grader
venvs; agents only ever see the agent venvs. Next to each agent venv,
`setup_envs.sh` writes `<venv>.requirements.txt` (`uv pip freeze`) and
`<venv>.manifest.json` (every file's content hash and every symlink's target), which the harness uses to
detect and undo changes an agent makes. The harness refuses to start if any
grader or agent interpreter is missing.

Run the harness with any Python that has pyyaml. The 3.3 grader venv works:

```bash
PY=~/.cache/des-evals/airflow-3.3/bin/python
```

## Usage

```bash
# Grader self-test, no LLM. Reference and alt_reference must pass. Fixture and
# every mutant must fail at least one primary check.
$PY evals/harness/run_eval.py --cases evals/airflow/cases --self-test [--case ID ...] [--split all]

# Check which skills each arm loads, no LLM.
$PY evals/harness/run_eval.py --arm skill --inventory-only

# Agent runs, one arm per invocation and per output dir.
$PY evals/harness/run_eval.py --cases evals/airflow/cases --arm baseline \
    --models google-vertex-anthropic/claude-sonnet-5-5@default,google-vertex-anthropic/claude-opus-5-5@default,google-vertex-anthropic/claude-fable-5-1@default \
    --runs 3 --parallel 4 --split dev --out evals/airflow/results/dev-baseline
$PY evals/harness/run_eval.py ... --arm skill --out evals/airflow/results/dev-skill

# Report: paired deltas need both arms.
$PY evals/harness/report.py evals/airflow/results/dev-baseline evals/airflow/results/dev-skill \
    --out evals/airflow/results/dev-summary

# Replace local paths in result dirs written before sanitize.py existed.
python3 evals/harness/sanitize.py evals/airflow/results          # --check only reports
```

Other flags:
- `--case ID` (repeatable)
- `--run-offset N` (default 0): run indices start at `N+1`. Use it to add runs to
  an earlier campaign in a new `--out` dir, e.g. `--runs 1 --run-offset 2` runs
  only `run-3`. `report.py` merges the dirs: a `skipped_budget` row is replaced by
  the launched run with the same (case, arm, model, run), and its spend (paid
  infra attempts) is kept on the replacing row. Two launched rows for the same run
  abort the report. Dirs whose case hashes/splits or `skills/airflow` revisions
  disagree also abort it, unless `report.py --allow-mixed` is passed.
- `--skills-dir` (default `skills/airflow`)
- `--repo-skills-dir` (default `skills`)
- `--max-cost-usd` (campaign cap, default 60)
- `--max-run-cost-usd USD`: one per-run cap for every model (0 = none). Without
  it, each model gets its `DEFAULT_RUN_CAP_USD` entry in `run_eval.py`
  (Sonnet 5.5 $6, Opus 5.5 $12, Fable 5.1 $30, Sonnet 4.6 $6, Haiku 4.5 $2.5;
  others $5), scaled to price so an expensive model is not cut off early.
- `--max-run-cost-usd-by-model MODEL=USD,...`: per-model overrides (full id or a
  key such as `claude-opus-5-5`); wins over both of the above.
- `--no-sandbox`: skip `sandbox-exec` (contamination detection still runs)
- `--keep-workspaces`
- `--keep-traces`: copy the altimate-code trace (`trace.json`) or the Claude Code
  session transcript (`session.jsonl`, secrets redacted) into the attempt dir

Case ids that start with `_` (for example `_example_smoke`) are harness
examples. They run only when named with `--case`.

Cases are selected by `--split` (`dev`, `holdout`, `all`) and `--case`. The
`suite:` key in `case.yaml` (`hard` for the `hard-*` cases) is informational:
`--split dev` runs the core dev cases and the hard dev cases together, so run the
hard suite with `--case hard-...` (repeatable).

Per-case limits in `case.yaml`: `timeout_s` (wall clock, default 900, at most
3600) and `max_turns` (passed to the agent's `--max-turns`, default 40, at most
120). Values outside 1..3600 / 1..120 fail case validation. The `hard-*` cases use
`timeout_s: 3600` and `max_turns: 80`. `meta.json` records each case's limits.

- `--runner altimate-code|claude-code` (default `altimate-code`; also on `run_triggers.py`)
- `--resume`: keep the finished runs in `--out/runs.jsonl` and launch only missing
  runs and unscored ones (`infra_error`, including killed runs, `harness_error`,
  `skipped_*`). A rerun keeps its earlier attempts (and their spend) and numbers
  new attempts after them. Arm, runner and models must match `meta.json`
  (`run_triggers.py`: runner and models). `run_eval.py` also refuses to resume when a selected case's
  content hash or `skills/airflow` (skill arm) differs from `meta.json`: start a new `--out` dir
  instead. `--runs` may grow on resume. Works with
  both runners on both scripts (claude-code resume verified with 2.1.286).

## Claude Code runner (`--runner claude-code`)

Runs `claude -p --model <m> --max-turns <case.max_turns> --output-format stream-json
--verbose --dangerously-skip-permissions --strict-mcp-config --mcp-config=<empty> -- <prompt>`
with cwd = workspace, under the same timeout, TMPDIR, sandbox, agent venv, pip
isolation and venv guard as altimate-code. Models are Claude Code ids
(default `claude-sonnet-5-5,claude-opus-5-5,claude-fable-5-1`).

Auth uses the user's subscription through an OAuth token. Each attempt has its
own empty config dir, so a logged-in `claude` on the host is never used directly.
The harness refuses to start unless one of these is set:

- `CLAUDE_CODE_OAUTH_TOKEN`: one token for the whole campaign (for example from
  `claude setup-token`, injected by a secrets wrapper).
- `EVAL_CLAUDE_TOKEN_CMD`: a command that prints a current access token on
  stdout, e.g. one that reads the token of a logged-in Claude Code and refreshes it
  when it is close to expiry. It is split with `shlex` (no shell) and run once at
  start-up to fail fast, then again right before **each** attempt (task and trigger
  runs). Its token goes to that attempt only, as `CLAUDE_CODE_OAUTH_TOKEN`, and wins
  over an inherited one. Its output is never logged; the variable itself is removed
  from agent and grader envs. A non-zero exit, an empty or multi-line output, or a
  timeout (180 s) is an `infra_error` "token command failed", retried like any
  infra error. An auth failure from Claude Code (401, expired OAuth token,
  "Invalid API key · Please run /login") is also an `infra_error`; its retry runs
  the command again, so it gets a fresh token. Long campaigns survive token expiry
  this way.

```bash
export EVAL_CLAUDE_TOKEN_CMD="/path/to/print-claude-token"   # or: export CLAUDE_CODE_OAUTH_TOKEN=...
$PY evals/harness/run_eval.py --runner claude-code --arm skill --split dev --runs 3 --parallel 3 \
    --out ~/.cache/des-evals/cc-dev-skill
```

Isolation, in addition to the list under "Isolation: what each agent run sees"
below (verified with 2.1.286):
- **`CLAUDE_CONFIG_DIR`**: a fresh `<scratch>/claude-config` per attempt, so the
  user's `~/.claude` settings, hooks, plugins, MCP servers, skills, sessions and
  `~/.claude.json` never load. The arm's skills are copied flat into
  `$CLAUDE_CONFIG_DIR/skills/<name>/` (Claude Code lists them with source
  "User"; `_shared` and other `_`/`.` dirs are never skills).
- **No CLAUDE.md / AGENTS.md:** Claude Code loads `CLAUDE.md`, `.claude/CLAUDE.md`
  and `AGENTS.md` from every ancestor of the workspace, which includes
  `~/.claude/CLAUDE.md` for any workspace under `~`.
  `CLAUDE_CODE_DISABLE_CLAUDE_MDS=1` turns that off. The ancestors found are
  recorded in `meta.json` (`isolation.ancestor_memory_files_disabled`), and the
  sandbox denies reads of `~/.claude`, `~/.claude.json`, `~/CLAUDE.md` and `~/AGENTS.md`.
- **Env:** inherited `CLAUDE*`/`ANTHROPIC*` variables are removed (the harness may
  itself run inside Claude Code), except `CLAUDE_CODE_OAUTH_TOKEN`. Auto-memory,
  telemetry, error reporting, surveys, marketplace auto-install and updates are
  off (`claude_code.ISOLATION_ENV`). `CLAUDE_CODE_TMPDIR` and zsh's `TMPPREFIX`
  point into the attempt's TMPDIR. Without that, Claude Code's messaging socket
  and the Bash tool's heredocs would go to `/tmp`, which the sandbox denies.
- **Sandbox:** writes only under scratch, the agent venv and `/dev`. Reads are
  denied for the same roots as altimate-code, plus the host Claude Code files. The
  ancestors of the scratch dir stay `stat`-able, but cannot be listed or read.
  Without that, `mkdir -p` and SQLite (Airflow's metadata DB) fail inside the
  workspace. The altimate-code profile is unchanged and still has this problem.
- **Inventory:** before the campaign, a local `/context` command runs under the
  agent env and sandbox. It makes no model call and returns the `system/init`
  event, each skill's source and any memory files. It is saved as
  `inventory-<arm>.json`. Each attempt's init event is checked again while the
  run streams. On a mismatch the run is killed (`harness_error`, `aborted`) and
  no further attempts start (`skipped_abort`). Checks: repo skills present,
  Airflow skills only in the skill arm, no MCP server, only built-in plugins, no
  auto-memory, no memory files, and no non-built-in skill outside the arm spec.
- **Parsing** (`grading.py` accepts both streams): `Skill` tool calls ->
  `skill_invocations` (`input.skill`); `Bash`/`Read`/`Edit`/`Write`/`Grep`/`Glob`
  inputs -> bash commands, edited files and the contamination scan (tool names
  are lowercased, `Bash` -> `bash`); the `result` event -> `num_turns`, usage and
  `total_cost_usd`. Graders get the raw stream as `--events`.
- **Cost:** a subscription is not billed per token. `cost_usd` and
  `cost_usd_equivalent` both hold Claude Code's API-equivalent `total_cost_usd`.
  That value drives per-run caps (estimated from streamed message usage at list
  prices until the result arrives) and the campaign budget.
- **Statuses:** `error_max_turns` -> `turn_limit`; wall clock -> `timeout`; an
  error result, API error, `api_retry` exhaustion or auth failure ->
  `infra_error`, retried 3 times with backoff (30, 60, 120 s). A run killed
  from outside (Claude Code exits 143 on SIGTERM, Popen reports -9 on SIGKILL)
  is an `infra_error` "killed" and is retried at most twice.
- **Usage (plan) limits:** a rejected `rate_limit_event` or a "hit your limit"
  message is an `infra_error` flagged `usage_limit`. All workers pause together
  (2, 4, 8, 16 min, at most 30 min in total), and these pauses are not counted
  as retries. When the limit persists, the campaign stops cleanly: unlaunched
  runs get `skipped_usage_limit` and the exit code is 3. Rerun the same command
  with `--resume`.
- **Secrets:** `sanitize.py` redacts `sk-ant-*` tokens (API keys `sk-ant-api03-…`
  and OAuth access tokens `sk-ant-oat01-…`), the literal value of
  `CLAUDE_CODE_OAUTH_TOKEN`, and every token fetched through `EVAL_CLAUDE_TOKEN_CMD`
  (registered at fetch time, whatever its shape), in every artifact. That covers raw `events.jsonl`
  and `stderr.log` (`redact_file`) and the optional `session.jsonl`
  (`--keep-traces`). `sanitize.py --check` also flags tokens.
- Tests: `tests/evals/test_claude_code.py` (recorded streams, no network),
  `tests/evals/test_harness_hardening.py` (signal isolation under a real
  `sandbox-exec`, broad-kill detection, killed runs, case limits) and
  `tests/evals/test_claude_code_integration.py` (marked `slow`; runs with
  `EVAL_RUN_SLOW=1` and either token variable).

## Isolation: what each agent run sees

Each run gets its own scratch directory under
`${EVAL_WORK_ROOT:-~/.cache/des-evals/work}`. The harness refuses to run if that
path is inside a git repo. Everything the agent may write lives in that scratch
dir, except the agent venv (see below).

- **Workspace:** a fresh copy of `fixture/`, `git init`-ed and committed.
  The agent's work is saved as `agent.patch` (a text diff), which excludes bytecode,
  `airflow.cfg`, `airflow.db` and `webserver_config.py` (created when an agent points `AIRFLOW_HOME` at its
  workspace) and shows binary files only as "Binary files differ".
- **Temp dirs:** `TMPDIR`, `TMP` and `TEMP` point to `<scratch>/tmp`, never the
  shared `/tmp`. Earlier campaigns shared `/tmp` and two runs read another case's
  leftovers (`hourly_pageviews`, `carrier_scorecard`).
- **`OPENCODE_TEST_HOME`:** a new empty dir. This hides `~/.claude/skills`,
  `~/.agents/skills` and `~/.altimate-code`, and makes the built-ins load from
  the embedded blob.
- **`XDG_CONFIG_HOME`:** a new empty dir. This drops the user's `config.json`,
  including its custom agents, temperature and default model.
- **`XDG_DATA_HOME` / `XDG_STATE_HOME`:** new per-run dirs, so altimate-code
  sessions, traces and tool output of other runs are not visible. The host's
  `~/.local/share/altimate-code/{auth.json,mcp-auth.json,bin,engine}` are
  symlinked in.
- **Credentials:** provider auth comes from the symlinked `auth.json`. Vertex
  also uses the inherited `GOOGLE_APPLICATION_CREDENTIALS`,
  `GOOGLE_CLOUD_PROJECT` and `VERTEX_LOCATION`. The harness never reads or
  prints any of them.
- **External skills:** `OPENCODE_DISABLE_EXTERNAL_SKILLS=1`.
- **Skills:** both arms get a **copy** of the repo skills, loaded through
  `OPENCODE_CONFIG_CONTENT={"skills":{"paths":[<copy>]}, "small_model": haiku, ...}`.
  The skill arm's copy also includes `skills/airflow/`. The repo checkout is
  never on a skills path, because graders and references live there.
- **Inventory check:** before any run, `altimate-code skill list --json` runs
  under the same env. The harness aborts if any of these hold:
  - an Airflow skill appears in the baseline arm
  - an Airflow skill is missing from the skill arm
  - a repo skill is missing from either arm
  - any skill loads from the repo checkout

  The inventory is saved to `inventory-<arm>.json`.
- **Scrubbed env vars:** `AIRFLOW*`, `OPENCODE_*` and `ALTIMATE_ROUTER_*` (the
  last group can swap models mid-run), plus inherited `VIRTUAL_ENV`,
  `PYTHONPATH`, `PYTHONUSERBASE`, `PIP_USER`/`PIP_TARGET`/`PIP_PREFIX` and temp
  vars.
- **Tooling, identical in both arms:** the case's **agent** venv is activated (on
  `PATH`, with `VIRTUAL_ENV` set); grader venvs and any inherited venv are
  removed from `PATH`. There is a private `AIRFLOW_HOME`,
  `dags_folder=<workspace>/dags`, examples are off, and the macOS fork-safety
  variables are set. This matches a user working in a project venv, so an agent
  can run `airflow dags test`, `pytest` and `ruff` if it chooses to.
- **pip:** `PIP_REQUIRE_VIRTUALENV=1` (a global pip found further down `PATH`
  refuses to install), `PYTHONUSERBASE`, `PIP_CACHE_DIR` and `UV_CACHE_DIR` are
  per run. `pip install` inside the agent venv works, like in a user's project.
- **Agent venv guard:** before and after every attempt the agent venv is
  compared with its manifest. If it changed, the harness restores it
  (`uv pip sync` to the frozen requirements, delete files not in the manifest,
  then `uv pip sync --reinstall` if it still differs) and records
  `agent_env_pre` / `agent_env_post` in `attempt.json`. The campaign also checks
  (and restores) each agent venv before it starts. An exclusive thread and file
  lock spans each attempt's pre-check, execution and post-check. Attempts using
  the same venv are serialized, including across harness processes; different
  venvs can run concurrently. No restore rewrites a venv used by another attempt.
- **macOS sandbox:** when `sandbox-exec` works, the agent runs under a
  per-run profile (Claude Code differences are listed in its section above) (`<scratch>/sandbox.sb`, see `IsolationRoots.sandbox_profile`):
  - writes are denied everywhere except the scratch dir, the agent venv,
    `~/.cache/altimate-code` (provider SDK cache) and `/dev`;
  - reads are denied for the repo checkout (worktree and main checkout), the
    results dir, sibling campaign directories identified by `meta.json` or
    `runs.jsonl`, all of `~/.cache/des-evals` and `$EVAL_ENV_ROOT`, and the whole
    work root (other runs' scratch dirs) except this run's
    scratch dir and the staged skills, `~/.local/share/altimate-code` except the
    linked files, user skill dirs (`~/.claude`, `~/.agents`, `~/.altimate-code`,
    `~/.codex`, `~/.opencode`), `/private/tmp`, `/private/var/tmp` and the
    harness's own temp dir. The agent venv and grader runtime packages remain
    readable; reads of grader venvs still count as transcript contamination;
  - process information is denied except within the same sandbox instance.
    The profile also denies `sysctl-read` for the `kern.proc` prefix: on macOS
    26 neither control alone blocks every argv query. Together they prevent
    `ps aux` enumeration and direct `KERN_PROCARGS2` reads for an outside PID.
    The regression runs an unprivileged, ad-hoc signed copy of `ps`, since the
    system's setuid `/bin/ps` cannot launch under `sandbox-exec` even without
    these rules. Claude Code and altimate-code local startup still work;
  - signals are denied except to processes in the same sandbox instance
    (`(deny signal)` + `(allow signal (target same-sandbox))`, both runners).
    An agent's `pkill -f airflow` or `kill <pid>` of the harness, a grader or a
    sibling run fails with `Operation not permitted`; its own children can still
    be stopped. Each `sandbox-exec` call is its own instance, so two attempts
    with identical profiles cannot signal each other. The harness (outside the
    sandbox) still stops agents on timeout and cost cap. Verified on macOS 26
    with Claude Code 2.1.286 and altimate-code 0.12.2.

  The harness stops the entire agent process group on every exit, including
  successful exits, and escalates to SIGKILL even when the leader has exited.
  Before copying or grading, it rejects external, dangling, cyclic and directory
  symlinks and planted workspace/destination root links as task failures. Safe
  internal file links are rebased into the grading copy. Agent-selected final
  and trace artifacts must also resolve inside the attempt's scratch directory.

  The agent's stdout/stderr are spooled in the scratch dir and copied to the
  results dir afterwards: node aborts at startup when its stdio is a file it is
  not allowed to read. Verified with altimate-code 0.12.2, node 22 and Python
  3.12 against Vertex.
- **Contamination detection (always on):** after each run, every tool call's
  paths (bash commands, `filePath`/`path`/`pattern` inputs) are checked against
  the same forbidden roots plus `/tmp`, `/var/folders` and the grader venvs.
  A reference the sandbox did not block sets `contamination_suspect: true` with
  the hits in `attempt.json` (`isolation.hits`); blocked attempts are listed in
  `isolation.denied_hits`. `runs.jsonl`, `meta.json` and the report count the
  suspect runs.
- **Broad kill commands (always on):** bash commands that kill processes by
  name or pattern (`pkill`, `killall`, `kill $(pgrep|ps|lsof ...)`,
  `... | xargs kill`, `kill -1`) are listed in `isolation.kill_commands` and set
  `kill_command: true` on the attempt and row. `meta.json`
  (`isolation.kill_command_runs`, `isolation.killed_attempts`) and the report
  count them. Without the sandbox such a command can kill sibling runs and graders.
- **Older campaigns:** `rescore_contamination.py <result dirs> --out <dir>` applies the
  same scan to stored `events.jsonl` (git-ignored, so only where still on disk). It infers
  each attempt's scratch dir from its events, treats the grader venv as the agent venv
  for campaigns without separate agent envs, and labels each hit's evidence `strong` or
  `weak` (a heuristic for triage; the flag is the detector's). Output:
  `contamination.jsonl`, `REPORT.md` + `results.json` (both tables, per-case deltas, conclusion check) and `report.py` output for `all/`,
  `excluding-flagged/` and `excluding-strong/`.


## Grading

`grade.py` runs as
`<case env python> grade.py --workspace DIR --events EVENTS.jsonl --out RESULT.json`.

- The run's cwd is the case dir.
- `EVAL_HARNESS_DIR` and `EVAL_CASE_DIR` are set.
- It receives a **copy** of the final workspace.

The result has this shape:

```json
{"checks": [{"name": "...", "kind": "primary|secondary", "passed": true, "detail": "..."}],
 "primary_pass": true, "primary_score": 1.0, "secondary_score": 0.67}
```

Check kinds:
- **Primary checks** test behavior. Examples: the DAG imports in the target
  env, `airflow dags test` succeeds, tasks and deps are as expected, output data
  is correct, schedule and data intervals are right (checked via timetable
  APIs), re-runs are idempotent without clobbering neighbouring partitions, and
  the agent's tests catch planted bugs.
- **Secondary checks** are process and style. Examples: verification commands
  were run, ruff AIR is clean, and there are no deprecation warnings.

### Helper API (`grading.py`)

Import it in `grade.py` like this:

```python
import os, sys
sys.path.insert(0, os.environ["EVAL_HARNESS_DIR"])
import grading as g
py = sys.executable            # grade.py already runs under the case's env python
```

| Helper | Returns / notes |
|---|---|
| `airflow_env(workspace, extra=None, airflow_home=None, env_py=None) -> dict` | Env with a fresh temp `AIRFLOW_HOME` (sqlite), `dags_folder=<ws>/dags`, examples off, and inherited `AIRFLOW__*`/`AIRFLOW_CONN_*`/`AIRFLOW_VAR_*` scrubbed. Pass Variables and Connections through `extra`. |
| `import_dags(env_py, workspace, env=None) -> dict` | Parses in a subprocess with the version-appropriate DagBag. Returns `{"dags": {id: {tasks, task_details, deps, schedule, timetable, timetable_summary, catchup, start_date, end_date, max_active_runs, tags, params, default_args, fileloc}}, "import_errors": {relpath: tb}, "warnings": [...], "airflow_version", "ok", "probe_error"}` |
| `deprecation_warnings(import_result, workspace_only=True)` | Deprecation warnings raised by workspace files while parsing |
| `run_dags_test(env_py, workspace, dag_id, logical_date=None, env=None, timeout=300, conf=None) -> DagTestResult` | Unpacks as `ok, log = ...`. `.runs` holds the DagRun and task states read from the DB, and `.failed_tasks()` lists failed tasks. `ok` needs exit code 0 **and** every DagRun in state `success`. Reuse `env` to re-run against the same DB. Tasks really re-execute on both 3.3 and 2.11. |
| `dag_runs(env_py, workspace, dag_id, env)` | DagRuns with per-task states |
| `run_python_in_env(env_py, code, workspace, env=None, timeout=300) -> ProcResult` | Arbitrary probe. `.ok`, `.stdout`, `.stderr`, `.tail()` |
| `probe_json(env_py, code, workspace, env=None) -> (RESULT, ProcResult)` | The probe assigns `RESULT`. The prelude provides `dagbag()`, `get_dag(id)`, `core_timetable(dag)`, `scheduled_intervals(dag, earliest, n=3, catchup=True)` and `manual_interval(dag, run_after)`. It works on 3.3 and 2.11. |
| `ruff_air(env_py, workspace, paths=("dags",), select="AIR", preview=False) -> [{"code","filename","line","message"}]` | Runs with `--isolated`, so the workspace's ruff config is ignored |
| `air_select_for(airflow_version)` | `"AIR"` for 3.x. `"AIR0,AIR2"` for 2.x, because AIR3xx flags correct 2.x code. |
| `run_pytest(env_py, workspace, paths=("tests",), env=None, timeout=600, extra_args=()) -> PytestResult` | Fields are listed below the table. |
| `copy_workspace(workspace, overlays=(), dest=None) -> Path` | Copy with overlays applied, for example to swap a hidden buggy DAG under the agent's tests |
| `apply_overlay(overlay, dest)` | Overlay copy. A top-level `_DELETE` file lists paths to remove. |
| `load_events(path)`, `tool_uses(events, tool=None)`, `skill_invocations(events)`, `bash_commands(events)`, `ran_command_matching(events, regex)`, `edited_files(events)`, `usage(events)`, `termination(events)`, `error_messages(events)` | Parsers for the altimate-code JSON event stream |
| `Grader()` with `.primary(name, passed, detail)`, `.secondary(...)`, `.run(name, fn, kind)` and `.write(out)` | `.run` records an exception as a failed check. It never becomes a grader crash. |
| `parse_args()` | The standard `--workspace/--events/--out` CLI |
| `standard_secondary_checks(grader, env_py, workspace, events, import_result=None)` | Adds three checks: verification commands were run, ruff AIR is clean (version-aware), and there are no deprecation warnings |

`PytestResult` fields:
- `status`: `passed|failed|collection_error|no_tests|timeout|error`
- counts: `passed`, `failed`, `errors`, `skipped`
- `tests`, `collection_errors`
- `behavioral_failures`: failures that were **not** import or collection errors
- `caught_bug`: the suite ran and at least one test failed for a behavioral reason
- `summary()`

### Rules for case authors

- Compute expected data from the pristine case dir (`EVAL_CASE_DIR/fixture/...`),
  never from the agent's workspace.
- Delete agent-produced outputs before executing the DAG. Only what the DAG
  writes counts. See `_example_smoke/grade.py`.
- Use a fresh `airflow_env()` per scenario. Reuse one env only when the scenario
  needs a second run against the same DB.
- Style is secondary unless it breaks the target version at runtime.
- Mutants are overlays applied on top of **fixture + reference**. Each one must
  fail at least one primary check. `alt_reference` is applied on top of the
  fixture and must pass.

## Results layout (`--out DIR`)

```
meta.json                    reproducibility: altimate-code version, models, env versions (python/airflow/ruff/
                             pytest/duckdb/pandas), agent env fingerprints, isolation settings, cost-correction
                             gate per model, sha256 of every case dir, staged skills, airflow skills, harness;
                             repo HEAD; timestamps; per-model run caps; budget spent; status counts;
                             contamination suspects, broad-kill runs, killed attempts and agent-env
                             restores; per-case timeout_s/max_turns; claude-code: Claude Code version
inventory-<arm>.json         altimate-code: `skill list --json`; claude-code: init event + `/context`,
                             both under the agent env
runs.jsonl                   one row per (case, model, run): final status, primary_pass/score, secondary_score,
                             cost (sum over all attempts), tokens, wall time, airflow skills used, retries,
                             contamination_suspect, kill_command, killed_attempts, agent_env_restored,
                             and every attempt
runs/<case>/<model>/run-N/attempt-K/
    events.jsonl stderr.log final.md agent.patch grade.json grade.log attempt.json
    [trace.json | session.jsonl]  (--keep-traces)
```

Every committable file the harness writes (`meta.json`, `inventory-*.json`,
`runs.jsonl`, `attempt.json`, `grade.json`, `final.md`, `agent.patch`,
`selftest.json`, trigger `summary.json`/`REPORT.md`, report `results.json`/`REPORT.md`)
goes through `sanitize.py`: the repo checkout becomes `<repo>`, the work root
`<work>`, temp roots `<tmp>` and the home dir `~`. Raw transcripts and logs stay
local (`.gitignore`), as do crash dumps and backups (`*.harness-exception`,
`*.prev-*`, `*.bak`, ...). `tests/evals/test_sanitize.py` fails if a committable
file under `evals/airflow/results` holds an absolute `/Users/`, `/home/` or
`/private/tmp` path.

Attempt statuses:
- `ok`: primary checks passed
- `task_fail`
- `timeout`: wall clock
- `turn_limit`: altimate-code `why_harness_stopped=budget-exhausted`, Claude Code
  `error_max_turns`
- `cost_limit`: per-run cap
- `infra_error`: no model step completed, a provider/auth/rate-limit error ended
  the run, or the agent was killed from outside (reason `killed by signal N`:
  return code `-N` or `128+N` for SIGHUP/SIGINT/SIGKILL/SIGTERM, no final
  result/termination event, and not stopped by the harness for timeout or cost)
- `grader_error`
- `harness_error`: the harness itself raised, or (claude-code) the run was
  aborted on an inventory mismatch. Usage and cost of a run that already
  happened are kept in `attempt.json` and `runs.jsonl`, with the traceback.
- `skipped_budget`: campaign cap reached before launch
- `skipped_usage_limit` (claude-code): the campaign stopped on a plan usage limit
- `skipped_abort` (claude-code): an earlier attempt aborted the campaign

Rules:
- `infra_error` is never graded and every attempt is kept. altimate-code retries
  it at most twice (20, 40 s); claude-code three times (30, 60, 120 s). A killed
  run is retried at most twice on either runner. A model that is not enabled for
  the project (Vertex 404 "Publisher model ... was not found", 403
  `PERMISSION_DENIED`) is not retried.
- A run that hits a limit but still passes grading counts as `ok`.
- `report.py` excludes `infra_error`, `grader_error`, `harness_error` and the
  `skipped_*` statuses from pass rates and reports them separately. Spend totals
  include every attempt.

## Cost

`grading.usage(events, model, correct)` sums altimate-code's `step_finish` costs
and records three numbers per attempt: `cost_usd` (used for caps and budgets),
`cost_reported_usd` (raw) and `cost_list_price_usd` (recomputed from tokens with
`MODEL_PRICING_PER_MTOK`, list prices per MTok):

| Model | input | output | cache read | cache write (5m) |
|---|---|---|---|---|
| Haiku 4.5 | 1 | 5 | 0.10 | 1.25 |
| Sonnet 4.6 | 3 | 15 | 0.30 | 3.75 |
| Sonnet 5.5 | 2 | 10 | 0.20 | 2.50 |
| Opus 5.5 | 4 | 20 | 0.20 | 5.00 |
| Fable 5.1 | 10 | 50 | 0.25 | 12.50 |

altimate-code 0.12.x with `google-vertex-anthropic` reports `tokens.input`
including cache reads/writes and charges all of it at the uncached rate on top
of the cache charges. The correction (`grading.step_cost`) is gated: it runs
only for that provider and version (`cache_correction_applies`), and, for a
model with a pricing row, only on steps whose reported cost equals the
double-counted price (`double_counted_steps` in `attempt.json`). Any other
provider, version or model that reports correctly keeps its reported cost.
Verified on 0.12.2: Haiku 4.5 and Sonnet 4.6 steps still double count.

## Trigger evals (`run_triggers.py`)

Checks whether the right Airflow skill fires, and whether all of them stay quiet
on near-misses. Nothing is graded except skill invocation.

- `evals/airflow/triggers/queries.json` lists the queries. Each names a context
  (`airflow2`, `airflow3`, `dbt`, `python`) that maps to a small fixture under
  `evals/airflow/triggers/fixtures/`, and an `expected` Airflow skill (or `null`
  for a near-miss).
- Isolation is the same as the **skill** arm of `run_eval.py`: all repo skills
  plus `skills/airflow`, with the same inventory check, sandbox, per-run temp
  and data dirs, agent venv guard and contamination scan. Airflow contexts
  activate the matching agent venv. `dbt` and `python` contexts get no Airflow
  venv or `AIRFLOW_*` variables.
- Each run uses `--max-turns 4` by default. The agent usually does not finish;
  a skill counts as fired if the agent called it through the `skill` tool, or if
  the trace shows it auto-loaded.
- Wall clock per run: `--timeout-s` (default 300). Attempt statuses are `ran`,
  `timeout`, `cost_limit` and the infra/harness statuses of `run_eval.py`
  (killed runs included), retried the same way.
- Per-run caps default to 0.4x the task caps (`TRIGGER_CAP_FRACTION`);
  `--max-run-cost-usd` and `--max-run-cost-usd-by-model` work as in `run_eval.py`.
- Run outcomes: `hit`, `hit_plus` (the expected skill plus another Airflow skill),
  `confused` (only a different Airflow skill), `miss`, `false_fire` and `quiet`.
- Metrics per skill: recall, precision, confusion rate and near-miss false-fire
  rate. They are reported overall and per model.

```bash
$PY evals/harness/run_triggers.py --runs 2 --max-turns 4 --max-cost-usd 40 \
    --out evals/airflow/results/triggers-<date>
$PY evals/harness/run_triggers.py --report-only --out evals/airflow/results/triggers-<date>
```

Output: `meta.json` records the sha256 of `skills/airflow` before and after the
campaign, plus the sha256 of the queries and each fixture. The directory also
holds `inventory-skill.json`, `runs.jsonl`, `runs/<query>/<model>/run-N/attempt-K/`,
`summary.json` and `REPORT.md`.


## Known limits

- The campaign cap is checked before each launch, so in-flight runs can overshoot
  it by up to `parallel x per-run cap`.
- altimate-code cost comes from its `step_finish` events (Claude Code: see
  "Cost" in its section). The altimate-code system prompt alone is about 59k
  input tokens: a trivial Haiku turn costs about $0.13 and a trivial Sonnet 4.6
  turn about $0.39.
- Auto-loaded skills (`applyPaths`) do not emit a skill tool call. They are
  detected from the altimate-code trace, which the harness reads in place (in
  the run's private data dir) and does not copy unless `--keep-traces` is set.
- The sandbox is macOS only. Elsewhere (or with `--no-sandbox`) isolation relies
  on the per-run dirs plus contamination and broad-kill detection, which only see
  paths and commands that appear literally in tool calls (not ones computed inside
  a script), and nothing stops an agent from signalling other processes.
- If the harness itself is killed, agents keep running in their own sessions
  until they finish or hit their own limits; rerun with `--resume`.
- Parallelism is limited to one attempt per agent venv by the environment lease.
