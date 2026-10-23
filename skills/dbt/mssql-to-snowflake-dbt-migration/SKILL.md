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

### Phase 0 — Choose layering (ask ONCE, ≤20s)

Ask the user:

> Which layering should the Snowflake dbt project use?
> **1. Medallion** (bronze → silver → gold) — recommended for most analytics workloads.
> **2. Data Vault 2.0** (hubs / links / satellites) — pick if the source is heavily normalized OLTP and auditability matters.

Default to Medallion if the user doesn't answer in one exchange. Carry
the choice through every object converted.

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
| `IDENTITY(1,1)` columns | `AUTOINCREMENT` on `CREATE TABLE`, OR `ROW_NUMBER() OVER (ORDER BY ...)` in a model, OR a NULL-safe surrogate via `{{ dbt_utils.generate_surrogate_key([...]) }}` | **TRAP:** dbt models don't own identity sequences. Do NOT hand-roll `md5(concat(col1, col2, ...))` — Snowflake `CONCAT` returns NULL on any NULL arg, so a business key with one NULL part becomes NULL for many rows, and they all collide on the same hash. `dbt_utils.generate_surrogate_key` is NULL-safe (it coalesces each arg to `''_dbt_utils_surrogate_key_null_'` before hashing). |
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

Compute the run timestamp once, up front — the same `TS` is reused in
Phases 4, 5, 6, and 7:

```bash
TS="$(date +%Y%m%d_%H%M%S)"
ISOLATED_SCHEMA_PREFIX="MIGRATION_${TS}"
```

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

Deploy to the isolated schema the user confirmed — **never** `--target
prod`. Enforce isolation by **one** of these two methods (Method 1 is
required when the project is standard; see Prerequisites). **Use the
same `TS` from Phase 4** — do not recompute.

**Method 1 — dedicated target with env-var-driven `schema:` in
`profiles.yml`:**
```yaml
# profiles.yml  (user adds this once; the skill does NOT edit profiles.yml)
<project>:
  outputs:
    migration:
      type: snowflake
      database: <db>
      schema: "{{ env_var('DBT_SCHEMA') }}"   # dynamic — set per run
      warehouse: <wh>
      role: <role>
      # ...other connection details...
```
Then:
```bash
# TS and ISOLATED_SCHEMA_PREFIX come from Phase 4 — do not recompute.
export DBT_SCHEMA="${ISOLATED_SCHEMA_PREFIX}"

dbt build \
  --select <migrated_models_only> \
  --target migration \
  --fail-fast
```

**Method 2 — custom `generate_schema_name` macro** that reads
`var('target_schema')`:
```bash
dbt build \
  --select <migrated_models_only> \
  --target <non_prod_target> \
  --vars "{target_schema: \"${ISOLATED_SCHEMA_PREFIX}\"}" \
  --fail-fast
```
**Only use Method 2** if `macros/get_custom_schema.sql` (or equivalent)
exists and reads the var. Without it, `--vars` is a no-op and the build
lands in the default schema of `<non_prod_target>` — may collide with
shared dev tables.

**Both methods must:**
- Scope the build with `--select <migrated_models_only>` (space- or
  comma-separated) — NOT the whole project. Otherwise unrelated models
  are rebuilt and the "isolated schema" claim becomes false.

**Verify objects actually landed in the isolated schema prefix** before
reporting. Match with `ILIKE` + prefix so dbt's `+schema:` suffix
(`_BRONZE`, `_SILVER`, etc.) doesn't cause a false negative:
```sql
SELECT table_schema, table_name, table_type, row_count
FROM <db>.INFORMATION_SCHEMA.TABLES
WHERE table_schema ILIKE :isolated_schema_prefix || '%'
ORDER BY table_schema, table_name;
```
Or, more robustly, parse `target/run_results.json` from the dbt run and
check that every migrated node's `relation_name` references a schema
starting with `MIGRATION_<ts>` — this handles custom `generate_schema_name`
logic without second-guessing it.

If zero rows match (or `run_results.json` shows writes to a schema that
doesn't start with the prefix), the schema isolation did not work — stop
and report.

**Hard stop:** if `dbt build` fails OR the verification query returns
zero rows OR `run_results.json` shows an off-prefix write, stop and
report. Do not proceed to parity against an empty / wrong schema.

### Phase 6 — Parity validation (≤90s) — MANDATORY HARD STOP

Parity runs **after** the build, against the materialized relations in
`MIGRATION_<timestamp>` — not against compiled SELECTs.

Use the Altimate `data-parity` sub-task — do not hand-roll per-model
SQL unless `altimate-code` is unavailable. Pass the prompt via file:
```bash
if command -v altimate-code >/dev/null 2>&1; then
  cat > /tmp/mssql-parity-prompt.txt <<'EOF'
For each migrated dbt model in MIGRATION_<timestamp>, run data-parity
against the source MS SQL object. Use engine-neutral checks: row counts,
per-column aggregate (count/sum/min/max/null-count where typed), and a
keyed-sample diff for 1000 random keys. Mark PASS/FAIL per object. Stop
on first FAIL and surface the row-level diff.
EOF
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

Stage only paths that actually changed — in standard dbt, `sources.yml`
lives inside `models/` (under `model-paths`), and `dbt_project.yml` only
needs staging if it was edited.

**Branch name must include `TS`** so a re-run doesn't collide. Fail
loudly if the branch already exists — do NOT silently fall through and
commit on whatever branch happens to be current (which may be `main`):

```bash
set -e   # fail on any non-zero exit — do not silently continue
cd "<dbt_project_root>"

# TS was computed in Phase 4.
BRANCH="migration/mssql-to-snowflake-${TS}"
git checkout -b "$BRANCH"   # fails if the branch exists; set -e stops the script

# Stage with explicit allow-listed paths — git diff --cached --quiet
# checks the INDEX (which is empty before `git add`), so using it as a
# gate silently skips untracked files like a new generate_schema_name
# macro. Just add what the Phase 1 allow-list permits.
git add models/

# Method 2 (custom generate_schema_name) requires a new macro — if it
# was created in this run, stage it explicitly. (Phase 1's allow-list
# otherwise forbids macros/.)
if [ -f "macros/get_custom_schema.sql" ] && \
   git status --porcelain macros/get_custom_schema.sql | grep -q '^??'; then
  git add macros/get_custom_schema.sql
fi

# seeds/ only if this run added a seed
git status --porcelain seeds/ | grep -q . && git add seeds/

# dbt_project.yml only if modified
[ -n "$(git status --porcelain dbt_project.yml)" ] && git add dbt_project.yml

cd -   # back to repo root

# Commit message via file (quoted heredoc — no shell expansion of
# <scope> / <layering> text, which may contain shell metacharacters).
cat > /tmp/mssql-commit-msg.txt <<EOF
Migrate <scope> from MS SQL to Snowflake dbt (<layering>) — ${TS}
EOF
git commit -F /tmp/mssql-commit-msg.txt
```

Do not push unless the user asked for a PR.

Return exactly this dashboard:

```
# MS SQL → Snowflake dbt Migration Dashboard

Scope:        <N> objects (<N> tables, <N> views, <N> procs)
Layering:     <Medallion | Data Vault 2.0>
Target:       <db>.MIGRATION_<timestamp>  (NOT prod)

## Conversion
Models created:   <N>  (bronze <n> / silver <n> / gold <n>)
                       (or hubs <n> / links <n> / sats <n>)
Sources defined:  <N>
Tests added:      <N>
TRAP rewrites:    <list of CROSS APPLY / CONCAT / collation / etc. applied>

## Deployment
dbt build:        PASS (<N> models, <N> tests, <seconds>s)
Objects landed:   <N> in <db>.MIGRATION_<timestamp>  (verified via INFORMATION_SCHEMA)

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
