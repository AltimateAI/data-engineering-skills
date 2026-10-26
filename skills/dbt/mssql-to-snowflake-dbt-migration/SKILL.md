---
name: mssql-to-snowflake-dbt-migration
description: |
  Convert MS SQL Server source code (stored procs, views, T-SQL scripts) into dbt models targeting Snowflake, with build-first-then-parity, isolated-schema deployment, and a migration dashboard. Use when:
  (1) User says "migrate this T-SQL to dbt on Snowflake", "convert these stored procs end-to-end", "move <schema> from SQL Server to Snowflake"
  (2) Source lives in a repo as `.sql` dumps OR behind a reachable MS SQL connection, AND source rows are available in Snowflake for parity (replicated, staged, or landable)
  (3) Target is a dbt project with a Snowflake adapter
  (4) User expects a layered architecture (Medallion or Data Vault 2.0), parity-validated output, and an isolated-schema deploy
  **Prefer `migrating-sql-to-dbt`** for generic SQL-to-dbt conversion with no cross-engine parity, no isolated deploy, and no T-SQL-specific traps.
  Target wall time: ≤7 min for ≤10 objects; scales roughly linearly.
---

# mssql-to-snowflake-dbt-migration

**Pick architecture → inventory source → convert → confirm → build to isolated schema → parity → verify → dashboard.**

## When NOT to use this skill

- Source is PostgreSQL / MySQL / Oracle / BigQuery (not T-SQL) → `migrating-sql-to-dbt`.
- Target is not Snowflake → `migrating-sql-to-dbt` + the appropriate warehouse skills.
- Just one T-SQL snippet with no isolated-deploy or parity requirement → `migrating-sql-to-dbt`.
- Enhancing an existing dbt model → `dbt-model-enhancement`.

## Prerequisites

```bash
command -v altimate-code     # strongly preferred — carries MS SQL + Snowflake adapters and data-parity
command -v dbt               # required for the deploy phase
command -v git               # required
```

Must have:
- A dbt project configured for Snowflake (`dbt_project.yml` + a working
  `profiles.yml` or env-var profile).
- A Snowflake role with `CREATE SCHEMA` on the target database and
  `USAGE` on a warehouse. The skill writes to an **isolated schema**,
  not prod.
- **A dedicated migration target in `profiles.yml` with a `schema:`
  override** (see Phase 5 Method 1). The skill refuses to deploy without
  it — the `--vars '{target_schema: ...}'` trick is a no-op on standard
  projects.
- **`dbt_utils` package installed** (`packages.yml` + `dbt deps`) — the
  rewrite table recommends `dbt_utils.generate_surrogate_key` as the
  NULL-safe way to port T-SQL `IDENTITY` columns. If `dbt_utils` isn't
  installed, add it before Phase 2 or avoid the IDENTITY mapping.
- Source access via **one** of:
  - `altimate-code` configured with an MS SQL connection
    (`altimate-code providers`), OR
  - A directory of `.sql` dumps already in the repo.
- **For parity**: source rows must be readable from Snowflake — either
  replicated (Fivetran/Airbyte/pre-existing bronze), or landable via
  stage + `COPY INTO`. Phase 6 hard-stops if neither is true.

If `altimate-code` is unavailable AND no dump exists, stop and tell
the user.

If `dbt` is not installed, Phase 5 cannot run — stop and tell the user.

## Time budget

Target end-to-end runtime: **≤7 min** (420s) for ≤10 objects; scales
roughly linearly beyond that. Hard ceiling **10 min** (600s). Per-phase
caps (sum = 420s):
Phase 0 ≤20s · Phase 1 ≤45s · Phase 2 ≤120s · Phase 3 ≤15s · Phase 4 ≤15s ·
Phase 5 ≤90s · Phase 6 ≤90s · Phase 7 ≤25s.

## Inputs

- **Source**: either (a) a reachable MS SQL connection, or (b) a repo path containing `.sql` dumps.
- **Target**: dbt project root (default: `pwd`).
- **Scope**: specific objects, a schema, or "all" (confirm if ambiguous).

## Workflow

### Phase 0 — Choose layering + initialise state (ask ONCE, ≤20s)

Ask the user:

> Which layering should the Snowflake dbt project use?
> **1. Medallion** (bronze → silver → gold) — recommended for most analytics workloads.
> **2. Data Vault 2.0** (hubs / links / satellites) — pick if the source is heavily normalized OLTP and auditability matters.

Default to Medallion if the user doesn't answer in one exchange.

**Initialise the run state immediately after the layering decision** —
Phase 2's conversion step calls `scripts/record_written.sh`, which
requires an active run. If init were deferred to Phase 4 (user
confirmation), Phase 2's writes would either fail with "no current
run" or write to a stale previous run that Phase 4's `init_run.sh`
then overwrites with an empty manifest.

```bash
scripts/init_run.sh <Medallion|DataVault> '<migrated_models_selector>' <dbt_root>
```

What it does (see `scripts/init_run.sh`):
- `source scripts/state.sh init` — creates a fresh `<run_id>` directory
  under `$(git rev-parse --git-dir)/skill/mssql_migration/<run_id>/`.
- Validates layering (`Medallion` or `DataVault`).
- Computes `TS` once and `ISOLATED_SCHEMA_PREFIX="MIGRATION_${TS}"`;
  all later scripts read these from state.
- Persists `REPO_ROOT`, `DBT_ROOT`, `TS`, `ISOLATED_SCHEMA_PREFIX`,
  `LAYERING`, `SCOPE_SELECTOR` into state.

The migrated-models selector can be refined in Phase 2 after inventory —
re-run `init_run.sh` with the updated selector to overwrite the state
value.

### Phase 1 — Inventory source (≤45s)

**Live MS SQL (via altimate-code):** pass the prompt via file to avoid
shell interpolation of DB/schema names (which may contain quotes):
```bash
if command -v altimate-code >/dev/null 2>&1; then
  cat > /tmp/mssql-inv-prompt.txt <<'EOF'
List all tables, views, and stored procedures in <db>.<schema> on the
configured MS SQL connection. Return name, type, and row count.
EOF
  altimate-code run "$(cat /tmp/mssql-inv-prompt.txt)" \
    --yolo --output /tmp/mssql-inventory.md --dir "$(pwd)"
fi
```

**Repo dump:**
```bash
find <path> -type f \( -name "*.sql" -o -name "*.SQL" \) | sort
```

Group by object type (table / view / proc) and print a short inventory.
If scope is "all" and the count exceeds 20, ask the user once to narrow
or confirm proceeding in one batch.

### Phase 2 — Convert T-SQL to Snowflake dbt (≤120s for ≤10 objects)

For each object:

**Medallion mapping**
- Source table → `sources.yml` entry + `models/bronze/stg_<name>.sql` (1:1, renamed columns, typed).
- View / simple SELECT → `models/silver/int_<name>.sql`.
- Stored procedure (reporting-style) → `models/gold/<name>.sql`, materialized `table` or `incremental` based on size.

**Data Vault mapping**
- Business key → `models/hubs/hub_<entity>.sql`
- Relationship → `models/links/link_<a>_<b>.sql`
- Descriptive attributes → `models/satellites/sat_<entity>.sql` with `load_date` + `record_source`.

**T-SQL → Snowflake rewrites — apply with care; silent-data-change traps
are called out explicitly. These do NOT fit a single-token substitution:**

| T-SQL | Snowflake / dbt | Notes |
|---|---|---|
| `GETDATE()` | `CURRENT_TIMESTAMP()` | OK |
| `ISNULL(a, b)` | `COALESCE(a, b)` | OK |
| `TOP n` | `LIMIT n` | OK |
| `[bracketed]` identifiers | double-quoted or bare | OK |
| `DATEADD(dd, n, d)` | `DATEADD(day, n, d)` | OK |
| `CONVERT(type, x)` (2-arg) | `x::type` | OK |
| `CONVERT(type, x, style)` with date/time style code | `TO_CHAR(x, '<fmt>')` / `TO_DATE(x, '<fmt>')` / `TO_TIMESTAMP(x, '<fmt>')` with explicit format model | **TRAP:** bare `::type` loses the style. Map `112` → `'YYYYMMDD'`, `120` → `'YYYY-MM-DD HH24:MI:SS'`, etc. by hand. Never drop the style silently. |
| `#temp` tables | CTEs or ephemeral models | OK |
| `CROSS APPLY <table_fn>(a)` | lateral join | OK: `CROSS JOIN LATERAL ...` works in Snowflake. |
| `CROSS APPLY (SELECT TOP 1 ... WHERE outer.key = ...)` (correlated TOP-1) | aggregated CTE + `JOIN` with `QUALIFY ROW_NUMBER() OVER (PARTITION BY key ORDER BY ...) = 1` | **TRAP:** `LATERAL FLATTEN` only expands VARIANT / ARRAY and will NOT work here. |
| `OUTER APPLY (SELECT ... WHERE outer.key = ...)` | aggregated CTE + `LEFT JOIN` (Snowflake has no `LEFT JOIN LATERAL` for subqueries) | **TRAP:** same reason — rewrite as a derived table joined on the correlation key. |
| `a + b` on strings | `a || b` | Both are NULL-propagating; semantics preserved. |
| `CONCAT(a, b, ...)` | `COALESCE(a::VARCHAR, '') \|\| COALESCE(b::VARCHAR, '') \|\| ...` | **TRAP:** T-SQL `CONCAT` treats NULL as `''` AND implicitly stringifies non-string args; Snowflake `CONCAT` returns NULL on any NULL arg, and `COALESCE(number, '')` errors with "Numeric value '' is not recognized" because the fallback is a VARCHAR and the first arg is a NUMBER. Cast each arg to VARCHAR before `COALESCE`. |
| `WHERE col = 'active'` (SQL Server default collation is case-insensitive) | `WHERE LOWER(col) = 'active'` or confirm data is already lowercased in bronze | **TRAP:** Snowflake is case-sensitive — `'Active'` will not match `'active'`. Audit WHERE / JOIN predicates on string columns. |
| `int_col / int_col` | `TRUNC(a / NULLIF(b, 0))` (default — matches T-SQL truncation + T-SQL error-on-zero becomes NULL, a deliberate change) | **TRAP:** T-SQL `int / int` TRUNCATES (`7/2 = 3`) and ERRORS on zero divisor; Snowflake returns a decimal (`3.5`) and never errors. Defaulting to `a::NUMERIC / NULLIF(b, 0)` would silently change `3` → `3.5` across every migrated query. `TRUNC()` preserves truncation; `NULLIF` turns the error into NULL, which must be called out as a deliberate behavior change in the dashboard. |
| `MERGE ... WHEN MATCHED THEN UPDATE WHEN NOT MATCHED THEN INSERT` | incremental model with `unique_key` + **dedup** + **lookback** | **TRAP:** Snowflake `MERGE` fails nondeterministically on duplicate source keys ("Duplicate row detected during DML action"), and a naive `is_incremental()` filter on `updated_at > max(updated_at)` drops late-arriving rows. Always: (1) dedup inside the model with `QUALIFY ROW_NUMBER() OVER (PARTITION BY <unique_key> ORDER BY updated_at DESC) = 1`, (2) include a lookback window in the `is_incremental()` filter (e.g. `updated_at > (SELECT MAX(updated_at) - INTERVAL '2 days' FROM {{ this }})`). |
| `MERGE ... WHEN NOT MATCHED BY SOURCE THEN DELETE` | **no direct equivalent** — flag for the user. Options: snapshot-based deletes, `delete+insert` incremental strategy with a hard-delete CTE, or a post-hook `DELETE`. | **TRAP:** standard `incremental` with `unique_key` loses deletions. |
| `IDENTITY(1,1)` columns | `AUTOINCREMENT` on `CREATE TABLE`, OR `ROW_NUMBER() OVER (ORDER BY ...)` in a model, OR a NULL-safe surrogate via `{{ dbt_utils.generate_surrogate_key([...]) }}` | **TRAP:** dbt models don't own identity sequences. Do NOT hand-roll `md5(concat(col1, col2, ...))` — Snowflake `CONCAT` returns NULL on any NULL arg, so a business key with one NULL part becomes NULL for many rows, and they all collide on the same hash. `dbt_utils.generate_surrogate_key` is NULL-safe (it coalesces each arg to `'_dbt_utils_surrogate_key_null_'` before hashing). |
| `DATETIME` (3.33ms precision) | `TIMESTAMP_NTZ(9)` | **TRAP:** reading legacy `DATETIME` with fractional-ms logic that assumed the 3.33ms rounding will drift. Cast and document. |
| cursor / `WHILE` loop | set-based rewrite | Flag if truly impossible — never port the cursor as-is. |
| `EXEC sp_...` dynamic SQL | reject — ask user | Never blindly convert. |

Delegate the batch conversion when possible. Pass source + prompt via
file for safety:
```bash
if command -v altimate-code >/dev/null 2>&1; then
  cat > /tmp/mssql-conv-prompt.txt <<'EOF'
Convert these T-SQL files to Snowflake dbt models using <layering>
layering. Write them under models/. Apply the T-SQL→Snowflake rewrites
from the project convention, paying attention to the TRAP rows (CROSS
APPLY correlated TOP-1, CONCAT NULL semantics, case-insensitive
collation, int division, MERGE WHEN NOT MATCHED BY SOURCE, DATETIME
precision). Preserve business logic. List every file written.
EOF
  altimate-code run "$(cat /tmp/mssql-conv-prompt.txt)" \
    --yolo --output /tmp/mssql-convert.md --dir "$(pwd)"
fi
```

**Fallback** (altimate-code not installed): convert one object at a
time, writing the dbt model file and its YAML entry, applying the
rewrite table above. This is slow — flag it to the user and keep scope
small.

Add a `sources.yml` entry for every raw table, and a minimal `_models.yml`
with `description`, `columns`, and `not_null`/`unique` tests for keys.

### Phase 3 — Compile check (≤15s)

Before asking the user to deploy, verify the converted code at least
compiles:
```bash
dbt deps >/dev/null 2>&1 || true
dbt parse
dbt compile --select <migrated_models>
```

**Hard stop:** if `dbt compile` fails, fix before Phase 4. Parity + the
user's confirmation are meaningless on broken SQL.

### Phase 4 — User confirmation (ask ONCE, ≤15s)

State was initialised in Phase 0 and populated through Phase 2
conversion. Here we only show the summary and ask for a go/no-go.

Before deploying, show:
- Count of models to be built
- Target Snowflake database and **isolated schema prefix** (e.g.
  `<db>.MIGRATION_<ts>` — note: if the project configures `+schema:
  bronze/silver/gold`, dbt's default `generate_schema_name` concatenates,
  so actual schemas will be `MIGRATION_<ts>_BRONZE`, `..._SILVER`, etc.
  All start with the prefix.)
- Materializations (view / table / incremental counts)
- Compile status (PASS)
- Any TRAP rewrites that were applied (list them — the user needs to know)

Ask:

> Deploy these N models to schemas starting with `<database>.MIGRATION_<ts>` on Snowflake now?
> Parity will run after the build, in the same schemas.

Wait for an explicit yes. Default is NO — do not deploy on silence.

### Phase 5 — Deploy to isolated schema (≤90s)

Both methods for schema isolation go through one script. The script
runs `dbt deps` first, then `dbt build` with `--select "$SCOPE_SELECTOR"`
(from state — guaranteed non-empty), then runs the manifest-based
isolation check — all in one process so state is loaded exactly once:

```bash
scripts/deploy_isolated.sh method1 [<non_prod_target>]   # recommended
# OR
scripts/deploy_isolated.sh method2 [<non_prod_target>]
```

**Method 1** (recommended for standard projects): dedicated target in
`profiles.yml` with `schema: "{{ env_var('DBT_SCHEMA') }}"`. The script
exports `DBT_SCHEMA="${ISOLATED_SCHEMA_PREFIX}"` from state, so the
schema can never be empty — unlike the inline-shell form in previous
rounds, where a missing preamble gave `DBT_SCHEMA=""` and silently
landed in the default schema.

**Method 2**: custom `generate_schema_name` macro reading `var('target_schema')`.
The script passes `--vars "{target_schema: \"${ISOLATED_SCHEMA_PREFIX}\"}"`.
Only use this if `macros/get_custom_schema.sql` (or equivalent) exists
and reads the var — otherwise `--vars` is a no-op.

**Isolation check — `scripts/isolation_check.py`.** Called at the end
of `deploy_isolated.sh`. The check:

- Reads selected `unique_id`s from `target/run_results.json` — the
  `unique_id` key has been top-level since dbt 1.5, works on every
  supported version.
- Looks up each node's `relation_name` in `target/manifest.json`
  (authoritative; `relation_name` is written at parse time on every
  supported version, including dbt 1.7 where `run_results.json` omits
  it).
- Includes `model.`, `snapshot.`, and `seed.` — all three materialise
  schemas, all three can leak out of the isolated prefix.
- Fail-closed on empty `ISOLATED_SCHEMA_PREFIX` (would otherwise match
  everything via `schema.startswith('')`).
- Hard-stops if `checked == 0` (silent-pass on an empty check is worse
  than any FAIL).
- Hard-stops on any node whose schema doesn't start with the prefix.

**Hard stop:** if `dbt build` fails OR the isolation check fails, stop
and report. Do not proceed to parity.

### Phase 6 — Parity validation (≤90s) — MANDATORY HARD STOP

Parity runs **after** the build, against the real materialised
relations. Dump the migrated relation_names via the script (which uses
`manifest.json` for `relation_name` lookup — version-stable, works on
dbt 1.7 where `run_results.json` omits `relation_name`):

```bash
# Save the skill-scripts dir BEFORE cd'ing — `scripts/` is next to this
# SKILL.md, NOT inside the dbt project. The script needs `target/*.json`
# which lives inside the dbt project, so we cd there, but we still need
# to call the script via an absolute path.
SKILL_SCRIPTS="$(cd "$(dirname "$0")/scripts" 2>/dev/null && pwd)"
# shellcheck disable=SC1091
source "$SKILL_SCRIPTS/state.sh" load
# shellcheck disable=SC1091
source "$SKILL_SCRIPTS/state.sh" validate ISOLATED_SCHEMA_PREFIX

cd "$REPO_ROOT/$DBT_ROOT"
python3 "$SKILL_SCRIPTS/parity_relations.py" > /tmp/mssql-migrated-relations.txt \
  || { echo "No migrated relations found — did Phase 5 build anything?"; exit 1; }

if command -v altimate-code >/dev/null 2>&1; then
  # Quoted heredoc + sed injection — safe against object names containing
  # $()/backticks. __PREFIX__ is a literal placeholder; sed interpolates
  # $ISOLATED_SCHEMA_PREFIX after the heredoc body is already fixed.
  cat > /tmp/mssql-parity-prompt.txt <<'EOF'
For each migrated dbt model whose relation_name is listed in
/tmp/mssql-migrated-relations.txt (these are the actual Snowflake
relations under schemas prefixed with __PREFIX__, including any
+schema suffixes like _BRONZE / _SILVER / _GOLD), run data-parity
against the source MS SQL object. Use engine-neutral checks: row counts,
per-column aggregate (count/sum/min/max/null-count where typed), and a
keyed-sample diff for 1000 random keys. Mark PASS/FAIL per object. Stop
on first FAIL and surface the row-level diff.
EOF
  sed -i.bak "s/__PREFIX__/${ISOLATED_SCHEMA_PREFIX}/g" /tmp/mssql-parity-prompt.txt \
    && rm -f /tmp/mssql-parity-prompt.txt.bak

  altimate-code run "$(cat /tmp/mssql-parity-prompt.txt)" \
    --yolo --output /tmp/parity.md --dir "$(pwd)"
fi
```

**Fallback** (no altimate-code): parity must be computed on **one engine**
— Snowflake. `HASH_AGG`, `IS NOT DISTINCT FROM`, and `FULL OUTER JOIN`
are not portable to MS SQL. The **source rows must exist in Snowflake**:

1. Replicated into Snowflake (Fivetran/Airbyte/pre-existing bronze).
   Use the replicated relation as the "source side".
2. Not yet in Snowflake. **Stop and tell the user:** parity needs both
   sides in one place; either (a) land the source into Snowflake first
   (temporary stage + `COPY INTO`), or (b) install `altimate-code`,
   which handles cross-engine compare natively. **Do NOT fabricate a
   PASS** and do NOT silently downgrade to a row-count-only check.

After the source side is in Snowflake, compare on Snowflake only. Use
**engine-neutral** checks (hashes from two engines aren't comparable):
- Row count equality on both sides.
- Per-column aggregate check: `COUNT(*)`, `SUM(col)` (numeric columns
  only), `MIN(col)`, `MAX(col)`, and null-count via `COUNT_IF(col IS NULL)`.
  **Do NOT use `COUNT(*) FILTER (WHERE col IS NULL)`** — Snowflake does
  not support the SQL-standard `FILTER (WHERE ...)` clause on aggregates
  and the statement will error with a syntax error. `COUNT_IF` is the
  Snowflake-native equivalent; `SUM(IFF(col IS NULL, 1, 0))` is another
  valid form.
- Keyed-sample diff: pick 1000 random keys on the source side and
  verify every column matches on the Snowflake side.

If parity cannot be computed for an object, report it as
**"parity not verified"** — not PASS.

**Hard stop:** any FAIL (or "parity not verified") blocks the dashboard
from showing PASS. Report the failing objects and the diff.

### Phase 7 — Commit + dashboard (≤25s)

**During Phase 2 conversion, record every file written** so staging
can scope to pipeline-only paths (not the whole `models/` directory —
unrelated WIP must not land in the migration PR):

```bash
scripts/record_written.sh models/bronze/stg_<name>.sql models/silver/int_<name>.sql ...
```

If delegating conversion to `altimate-code`, parse its "List every file
written" output and pass those paths to `record_written.sh`.

Then stage + commit via one script that loads state, creates the branch
`migration/mssql-to-snowflake-${TS}` (fails if it exists so re-runs
can't collide), stages exactly the recorded paths, and writes the commit
message via quoted heredoc + sed injection (so `<scope>` / `<layering>` /
object names containing `$` or backticks can't trigger shell expansion):

```bash
scripts/stage.sh
```

Do not push unless the user asked for a PR.

Return exactly this dashboard:

```
# MS SQL → Snowflake dbt Migration Dashboard

Scope:        <N> objects (<N> tables, <N> views, <N> procs)
Layering:     <Medallion | Data Vault 2.0>
Target:       <db>.MIGRATION_<ts>*  (NOT prod)

## Conversion
Models created:   <N>  (bronze <n> / silver <n> / gold <n>)
                       (or hubs <n> / links <n> / sats <n>)
Sources defined:  <N>
Tests added:      <N>
TRAP rewrites:    <list of CROSS APPLY / CONCAT / collation / etc. applied>

## Deployment
dbt build:        PASS (<N> models, <N> tests, <seconds>s)
Objects landed:   <N> in <db>.MIGRATION_<ts>*  (verified via INFORMATION_SCHEMA)

## Parity
PASS:             <N> / <N>
FAIL:             <N>  (details above if any)
Not verified:     <N>  (source not in Snowflake; details above)

## Next steps
- <bullet — e.g. "Promote MIGRATION_<ts> → prod via CI once reviewed">
- <bullet — e.g. "Schedule gold models in Airflow DAG X">
- <bullet — e.g. "Review sat_customer: 2 columns inferred as VARIANT, confirm">
```

## Anti-patterns (never apply)

- Deploy to `--target prod` from this skill.
- `dbt build` with no `--select` — rebuilds the whole project and
  breaks isolation.
- Rely on `--vars '{target_schema: ...}'` without a custom
  `generate_schema_name` macro — it's a no-op.
- Report a dashboard-level PASS without the INFORMATION_SCHEMA
  verification that objects actually landed.
- Run parity before `dbt build` — the dbt side doesn't exist yet.
- Compare `HASH_AGG` across MS SQL and Snowflake — hashes aren't
  portable.
- Downgrade parity to "row count only" when deep parity isn't feasible.
  Report "not verified" instead of fabricating a PASS.
- Map `CROSS APPLY` to `LATERAL FLATTEN` for anything other than
  VARIANT / ARRAY expansion.
- Map T-SQL `CONCAT` directly to Snowflake `CONCAT` without the
  per-arg `COALESCE` wrapper.
- Assume case-insensitive string comparisons in Snowflake.
- Port cursor loops as `WHILE` loops.
- Blindly convert `EXEC sp_...` dynamic SQL — ask the user.
- Hand-roll `HASH(*)` — not valid Snowflake.
- Use `COUNT(*) FILTER (WHERE ...)` — not valid Snowflake either. Use
  `COUNT_IF(...)`.
- Hand-roll `md5(concat(business_keys))` for surrogate keys — Snowflake
  `CONCAT` returns NULL on any NULL arg, so NULL keys collide. Use
  `dbt_utils.generate_surrogate_key([...])`.
- Default integer-division rewrite to `a::NUMERIC / b` without `TRUNC`
  and `NULLIF` — it silently changes T-SQL truncating `3` to `3.5`.
- Default `MERGE` rewrite to a plain `incremental` `unique_key` without
  a `QUALIFY` dedup and a lookback window — Snowflake MERGE fails
  nondeterministically on duplicate source keys, and the naive
  `is_incremental()` filter drops late-arriving rows.
- Use a fixed branch name (`migration/mssql-to-snowflake`) — re-runs
  collide. Include `TS`.
- Use `git diff --cached --quiet <path> || git add <path>` as a staging
  gate — the index is empty before `git add`, so this always passes and
  the path is never staged.
- Use `UNION` where the T-SQL used `UNION ALL` or vice-versa.
- Modify the MS SQL source (read-only).
- Interpolate schema / object / SQL text into shell commands or
  `git commit -m "..."` — always use temp files or heredocs.

## Non-goals

- No permission grants on Snowflake (roles, warehouses, grants).
- No MS SQL writes.
- No PR open unless the user asks.
- No promotion from `MIGRATION_<ts>` to prod — that's a separate flow.

## Behavior contract

- Never deploy without the user's explicit yes in Phase 4.
- Never claim parity PASS without a passing data-parity output; report
  "not verified" if the compare can't be run.
- Never deploy to prod — isolated schema only.
- Never claim deployment to a schema with zero objects in
  INFORMATION_SCHEMA.
- Never silently skip objects that failed to convert — surface them.
- Never run `dbt build` without `--select` scoped to the migrated models.
- Never interpolate schema / object / SQL text into shell commands.
