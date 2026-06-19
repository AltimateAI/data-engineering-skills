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

2. **Run altimate-code with the user's task:**
   ```bash
   altimate-code run "$ARGUMENTS" \
     --yolo \
     --output /tmp/altimate-result.md \
     --dir "$(pwd)"
   ```

3. **Surface the result verbatim:** read `/tmp/altimate-result.md` and present its contents to the user without re-summarising, re-formatting, or commenting. altimate-code has already produced the answer.

4. **On any altimate-code error** (`Unauthorized`, `Token limit reached`, `No provider configured`, warehouse credentials wrong, process timeout) — surface the error message to the user along with the fix from the skill body's failure-modes table. Do NOT fall back to native tools. The user invoked `/altimate` specifically to use altimate-code; falling back would defeat the purpose.

Task to delegate: $ARGUMENTS
