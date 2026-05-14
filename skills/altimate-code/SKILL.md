---
name: altimate-code
description: Delegates data engineering tasks to altimate-code, a specialized CLI agent with 100+ purpose-built data tools — SQL analysis, column-level lineage, dbt build/test/run, warehouse profiling, FinOps, and connectivity to Snowflake, BigQuery, Redshift, Databricks, Postgres, MySQL, DuckDB. Use this skill when the task needs live warehouse access, column lineage, multi-step data exploration, dbt builds against a real warehouse, or when the user explicitly invokes "altimate", "altimate-code", or "the data agent".
---

# altimate-code

altimate-code is a CLI AI agent that ships with native data engineering tools. This skill delegates work to it via its non-interactive `run` mode and presents the result back to the user.

## Prerequisite Check — ALWAYS DO THIS FIRST

Before invoking altimate-code, verify it is installed and on `PATH`:

```bash
command -v altimate-code
```

**If the command returns nothing (exit code 1), STOP and tell the user this exact message — do not proceed:**

> altimate-code is not installed. Install it with:
>
> ```bash
> npm install -g altimate-code
> ```
>
> Requires Node.js 20+. Docs: https://docs.altimate.sh · Source: https://github.com/AltimateAI/altimate-code · npm: https://www.npmjs.com/package/altimate-code
>
> After installing, run `altimate-code` once to configure it — this launches the TUI where you set up your LLM provider auth and warehouse connections. Then re-run your request and I'll delegate it.

Do not attempt to install altimate-code on the user's behalf — they may want a specific version, a different package manager (e.g. pnpm/yarn global), or to opt out entirely. Surface the command and let them decide.

If `command -v` fails but the user says it is installed, suggest checking `npm bin -g` is on `PATH`, or running `npm config get prefix` to find the global install location.

## How to Invoke

`altimate-code run` is non-interactive — it takes a message, executes the task, prints the final result to stdout, and exits.

**Minimal invocation:**

```bash
altimate-code run "<task description>" --yolo
```

**Recommended invocation** — captures the final response to a file and runs in the right directory:

```bash
altimate-code run "<task description>" \
  --yolo \
  --output /tmp/altimate-result.md \
  --dir "$(pwd)"
```

Then read `/tmp/altimate-result.md` and pass it straight back to the user.

### Key flags

| Flag | When to use |
|---|---|
| `--yolo` | Required for non-interactive — auto-approves tool calls. Without this it hangs on the first permission prompt. |
| `--output <path>` | Write the final assistant response to a file. Use `.md` or `.txt`. |
| `--dir <path>` | Run the agent in a specific directory (e.g. a dbt project root). Defaults to cwd. |
| `--model provider/model` | Override the model. Useful for fast/cheap exploration. |
| `--format json` | Emit raw JSON events instead of formatted output. Use only when post-processing programmatically. |
| `--continue` / `--session <id>` | Continue a previous altimate-code session. |

### Example invocations

**Find expensive queries in Snowflake:**

```bash
altimate-code run "Find the top 10 most expensive queries from the last 7 days in Snowflake and explain why each is slow." \
  --yolo --output /tmp/expensive.md
```

**Generate column-level lineage for a dbt model:**

```bash
altimate-code run "Show column-level lineage for the dim_customers model, including upstream sources and downstream consumers." \
  --yolo --dir "$(pwd)" --output /tmp/lineage.md
```

**Profile a table:**

```bash
altimate-code run "Profile the events table — row count, null distribution per column, cardinality, and top 5 values for low-cardinality columns." \
  --yolo --output /tmp/profile.md
```

## Presenting the Result

Read the output file with the Read tool and pass the content through to the user as-is. Do not re-summarize, re-format, or interpret — altimate-code has already produced the answer.

## Failure Modes

| Symptom | Likely cause | Fix |
|---|---|---|
| `altimate-code: command not found` | Not installed or not on `PATH` | Run `npm install -g altimate-code` (Node 20+). If installed but not found, check `npm bin -g` is on `PATH`. See https://docs.altimate.sh |
| Hangs after starting | Missing `--yolo`, waiting on a permission prompt | Re-run with `--yolo` |
| Output is empty | Task too vague, agent gave up | Re-run with a more specific prompt |
| "No provider configured" | LLM provider creds missing | Run `altimate-code providers` to set up auth |
| Warehouse errors mid-run | DB credentials not configured for altimate-code | Configure provider/warehouse auth in `~/.config/opencode/` or via env vars |

## Notes

- altimate-code runs its own LLM, separate from Claude Code's. Cost and rate limits accrue against altimate-code's configured provider, not Claude Code's.
- Sessions persist in altimate-code's local store — use `altimate-code session list` to find prior runs and `--continue` to resume.
- For long-running tasks, prefer `--output <file>` over scraping stdout.
