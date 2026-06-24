---
description: Delegate a task to altimate-code, the specialised data-engineering CLI agent (warehouse access, column-level lineage, cross-DB, FinOps, query optimization)
argument-hint: <task description>
---

The user explicitly invoked `/altimate` to delegate this task to altimate-code. You MUST run the task via the `altimate-code` CLI — do NOT attempt the work with native `Bash`/`Edit`/`Write` tools.

Workflow (follow in order, no skipping):

1. **Verify altimate-code is installed:**
   ```bash
   command -v altimate-code
   ```
   If it returns nothing, stop and tell the user:
   > altimate-code is not installed. Install with `npm install -g altimate-code` (Node 20+), then run `altimate-code` once to configure your provider/warehouse auth, then re-run `/altimate <task>`.

2. **Pick the agent persona** based on the user's task shape. Start cheap and escalate on failure — fast-edit handles most dbt/SQL work at 10–20× lower cost than builder.

   | Task shape | Use `--agent` |
   |---|---|
   | Any dbt / SQL task (rename, refactor, create, debug, structural) | `fast-edit` (default) |
   | Aggregation correctness on multi-table joins | `analyst` if fast-edit fails the user's verification |
   | Warehouse-state work (lineage, cost, parity, schema diff, PII, FinOps) | `builder` |
   | Vague debug ("X is broken") | **Stop — ask the user for the specific error before delegating.** |

   Decision rule: start with `fast-edit`. Only use `analyst` / `builder` when the cheap path fails for a documented reason.

3. **Run altimate-code with the chosen agent:**
   ```bash
   altimate-code run "$ARGUMENTS" \
     --agent <fast-edit|analyst|builder> \
     --yolo \
     --output /tmp/altimate-result.md \
     --dir "$(pwd)"
   ```

   **If this is a follow-up task in the same project** (the user invoked `/altimate` already in this conversation about the same dbt project / warehouse / data context), add `--continue` to resume the warm session — cache is hot, follow-on cost is materially lower:

   ```bash
   altimate-code run "$ARGUMENTS" \
     --agent <fast-edit|analyst|builder> \
     --yolo --output /tmp/altimate-result.md --dir "$(pwd)" \
     --continue
   ```

   Skip `--continue` if the user switched projects, switched debugging threads, or this is the first `/altimate` invocation in the conversation.

4. **Surface the result verbatim:** read `/tmp/altimate-result.md` and present its contents to the user without re-summarising, re-formatting, or commenting. altimate-code has already produced the answer.

5. **On any altimate-code error** (`Unauthorized`, `Token limit reached`, `No provider configured`, warehouse credentials wrong, process timeout) — surface the error message to the user along with the fix from the skill body's failure-modes table. Do NOT fall back to native tools. The user invoked `/altimate` specifically to use altimate-code; falling back would defeat the purpose.

Task to delegate: $ARGUMENTS
