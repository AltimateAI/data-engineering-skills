---
name: mssql-to-snowflake-dbt-migration
description: |
  Convert MS SQL Server source code (stored procs, views, T-SQL scripts) into dbt models targeting Snowflake. Use when:
  (1) User says "migrate this T-SQL to dbt on Snowflake", "convert these stored procs", "move <schema> from SQL Server to Snowflake"
  (2) Source lives in a repo as `.sql` dumps OR behind a reachable MS SQL connection
  (3) Target is a dbt project with a Snowflake adapter
  (4) User expects a layered architecture (Medallion or Data Vault 2.0) and parity-validated output
  Asks once for Medallion vs Data Vault, converts the code, validates with Altimate data-parity, confirms with the user, deploys to an isolated Snowflake schema, writes models to the repo, and ends with a one-screen migration dashboard. Target wall time: ≤7 min for ≤10 objects.
---

# mssql-to-snowflake-dbt-migration

**Pick architecture → read source → convert → parity-validate → confirm → deploy → dashboard.**

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
  not prod, until Phase 5.
- Source access via **one** of:
  - `altimate-code` configured with an MS SQL connection
    (`altimate-code providers`), OR
  - A directory of `.sql` dumps already in the repo.

If `altimate-code` is unavailable AND no dump exists, stop and tell
the user.

If `dbt` is not installed, Phase 5 cannot run — stop and tell the user.

## Time budget

Target end-to-end runtime: **≤7 min** (420s) for ≤10 objects; scales
roughly linearly beyond that. Hard ceiling **10 min** (600s). Per-phase
caps (sum = 410s):
Phase 0 ≤20s · Phase 1 ≤45s · Phase 2 ≤120s · Phase 3 ≤90s · Phase 4 ≤15s ·
Phase 5 ≤90s · Phase 6 ≤30s.

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

**Live MS SQL (via altimate-code):**
```bash
if command -v altimate-code >/dev/null 2>&1; then
  altimate-code run "List all tables, views, and stored procedures in <db>.<schema> on the configured MS SQL connection. Return name, type, and row count." \
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

**T-SQL → Snowflake rewrites to apply mechanically:**

| T-SQL | Snowflake / dbt |
|---|---|
| `GETDATE()` | `CURRENT_TIMESTAMP()` |
| `ISNULL(a,b)` | `COALESCE(a,b)` |
| `TOP n` | `LIMIT n` |
| `[bracketed]` identifiers | double-quoted or bare |
| `DATEADD(dd, n, d)` | `DATEADD(day, n, d)` |
| `CONVERT(type, x)` (2-arg) | `x::type` |
| `CONVERT(type, x, style)` with date/time style code (e.g. `112`, `120`) | `TO_CHAR(x, '<fmt>')` / `TO_DATE(x, '<fmt>')` / `TO_TIMESTAMP(x, '<fmt>')` with an explicit Snowflake format model — a bare `x::type` cast loses the style and may fail. Map the T-SQL style code (`112` → `'YYYYMMDD'`, `120` → `'YYYY-MM-DD HH24:MI:SS'`, etc.) by hand; do NOT drop the style silently. |
| `#temp` tables | CTEs or ephemeral models |
| `CROSS APPLY` | `LATERAL FLATTEN` / lateral join |
| `MERGE ... WHEN MATCHED` | incremental model with `unique_key` |
| cursor loops | set-based rewrite (flag if truly impossible) |
| `EXEC sp_...` dynamic SQL | reject — ask user, do not blindly convert |

Delegate the batch conversion when possible:
```bash
if command -v altimate-code >/dev/null 2>&1; then
  altimate-code run "Convert these T-SQL files to Snowflake dbt models using <medallion|data-vault> layering. Write them under models/. Apply the standard T-SQL→Snowflake rewrites and keep business logic identical. List every file written." \
    --yolo --output /tmp/mssql-convert.md --dir "$(pwd)"
fi
```

**Fallback** (altimate-code not installed): convert one object at a
time, writing the dbt model file and its YAML entry, applying the
rewrite table above. This is slow — flag it to the user and keep scope
small.

Add a `sources.yml` entry for every raw table, and a minimal `_models.yml`
with `description`, `columns`, and `not_null`/`unique` tests for keys.

### Phase 3 — Parity validation (≤90s) — MANDATORY HARD STOP

Use the Altimate `data-parity` sub-task — do not hand-roll per-model
SQL unless `altimate-code` is unavailable:

```bash
if command -v altimate-code >/dev/null 2>&1; then
  altimate-code run "For each converted dbt model, run data-parity against the source MS SQL object. Report row count delta, column schema diff, and per-column HASH_AGG signature grouped by primary key. Mark PASS/FAIL per object. Stop on first FAIL and surface the row-level diff." \
    --yolo --output /tmp/parity.md --dir "$(pwd)"
fi
```

**Fallback** (no altimate-code): parity must be computed on **one engine**
— Snowflake — because `HASH_AGG`, `IS NOT DISTINCT FROM`, and `FULL OUTER
JOIN` across engines are not portable (MS SQL Server lacks `HASH_AGG` and
only added `IS [NOT] DISTINCT FROM` in SQL Server 2022). Before running
parity, the **source rows must exist in Snowflake** — one of:

1. The source tables are already replicated into Snowflake (e.g. by
   Fivetran, Airbyte, a `COPY INTO` from a stage, or a pre-existing
   bronze layer). Use the replicated relation as the "source side".
2. The source rows do not exist in Snowflake yet. Stop and tell the
   user: data-parity needs both sides in one place; either (a) land
   the source into Snowflake first (temporary stage + `COPY INTO`),
   or (b) install `altimate-code`, which handles the cross-engine
   compare natively.

**After** the source side is in Snowflake, run on Snowflake only:
- `COUNT(*)` on both sides, AND
- `HASH_AGG(col1, col2, ..., colN)` on both sides over the fully
  enumerated SELECT list (NOT `HASH(*)` — that's not valid Snowflake), AND
- A `FULL OUTER JOIN ... ON a.col IS NOT DISTINCT FROM b.col` on every
  column, grouped per distinct row, to catch multiplicity differences.

Note: Phase 3 runs **before** Phase 5's `dbt build`, so the dbt side of
the compare must use the **compiled SELECT** (`dbt compile --select
<model>` then read `target/compiled/.../<model>.sql`) — not the
materialized relation, which doesn't exist yet.

**Hard stop:** any FAIL blocks deployment. Report the failing object
and the diff — do not deploy a partially-correct migration.

### Phase 4 — User confirmation (ask ONCE, ≤15s)

Before deploying, show:
- Count of models to be built
- Target Snowflake database/schema (should be an **isolated non-prod
  schema** — e.g. `<db>.MIGRATION_<timestamp>`)
- Materializations (view / table / incremental counts)
- Parity summary (all PASS)

Ask:

> Deploy these N models to `<database>.<isolated_schema>` on Snowflake now?

Wait for an explicit yes. Default is NO — do not deploy on silence.

### Phase 5 — Deploy + write to repo (≤90s)

Deploy to the isolated schema the user confirmed in Phase 4 — **never**
run `--target prod` from this skill. Use a dedicated non-prod target
(`dev`, `migration`, or a user-defined target) and enforce the isolated
schema by **one** of these three methods (verify which one before
building):

1. **Target-level `schema:` override** in `profiles.yml` under a
   dedicated migration target — e.g.
   ```yaml
   migration:
     type: snowflake
     schema: MIGRATION_20261023_HHMMSS
     ...
   ```
   Then: `dbt build --target migration --fail-fast`.
2. **`DBT_SCHEMA` env var** (if `profiles.yml` reads it via `{{ env_var('DBT_SCHEMA') }}`):
   ```bash
   DBT_SCHEMA="MIGRATION_$(date +%Y%m%d_%H%M%S)" \
     dbt build --target <non_prod_target> --fail-fast
   ```
3. **Custom `generate_schema_name` macro** that reads `var('target_schema')`:
   ```bash
   dbt build --target <non_prod_target> \
     --vars '{target_schema: "MIGRATION_<timestamp>"}' --fail-fast
   ```
   `--vars` is a **no-op** on a standard dbt-snowflake project without
   this macro; writes land in the default schema of `<non_prod_target>`
   and may collide with shared dev tables. Verify the macro exists in
   `macros/get_custom_schema.sql` (or similar) before relying on method 3.

Pick one — do not combine. If none are configured, stop and tell the
user how to add method 1 or 2 before deploying.

```bash
dbt deps >/dev/null 2>&1 || true
# then the one dbt build command for the chosen method, above.
```

**Hard stop:** if `dbt build` fails, stop and report. Do not retry
blindly. Do not promote to prod from inside this skill — promotion
is a separate, user-driven step.

Then commit. Stage only paths that actually changed — in standard dbt,
`sources.yml` lives inside `models/` (under `model-paths`), and
`dbt_project.yml` only needs staging if it was edited.

```bash
cd "<dbt_project_root>"
git checkout -b migration/mssql-to-snowflake

# Stage from the project root; `models/` already covers nested sources.yml
# and _models.yml files. Add macros/, seeds/, or dbt_project.yml only if
# they were actually modified in this run.
git add models/
git diff --cached --quiet macros/      || git add macros/
git diff --cached --quiet seeds/       || git add seeds/
[ -n "$(git status --porcelain dbt_project.yml)" ] && git add dbt_project.yml

cd -   # back to repo root
git commit -m "Migrate <scope> from MS SQL to Snowflake dbt (<layering>)"
```

Do not push unless the user asked for a PR.

### Phase 6 — Migration dashboard (≤30s)

Return exactly this:

```
# MS SQL → Snowflake dbt Migration Dashboard

Scope:        <N> objects (<N> tables, <N> views, <N> procs)
Layering:     <Medallion | Data Vault 2.0>
Target:       <db>.<isolated_schema>  (NOT prod)

## Conversion
Models created:   <N>  (bronze <n> / silver <n> / gold <n>)
                       (or hubs <n> / links <n> / sats <n>)
Sources defined:  <N>
Tests added:      <N>

## Parity
PASS:         <N> / <N>
FAIL:         <N>  (details above if any)

## Deployment
dbt build:    PASS (<N> models, <N> tests, <seconds>s)
Target:       <db>.<isolated_schema>

## Next steps
- <bullet — e.g. "Promote <isolated_schema> → prod via CI once reviewed">
- <bullet — e.g. "Schedule gold models in Airflow DAG X">
- <bullet — e.g. "Review sat_customer: 2 columns inferred as VARIANT, confirm">
```

## Anti-patterns (never apply)

- Deploy to `--target prod` directly from this skill.
- Blindly convert cursor loops to WHILE loops — rewrite set-based or flag.
- Blindly convert `EXEC sp_...` dynamic SQL — ask the user.
- Hand-roll `HASH(*)` as the parity signature — it's not a valid
  Snowflake expression.
- Use `UNION` where the T-SQL used `UNION ALL` or vice-versa.
- Modify the MS SQL source (read-only).

## Non-goals

- No permission grants on Snowflake (roles, warehouses, grants).
- No MS SQL writes.
- No PR open unless the user asks.

## Behavior contract

- Never deploy without the user's explicit yes in Phase 4.
- Never claim parity without a passing data-parity output.
- Never deploy to prod — isolated schema only.
- Never silently skip objects that failed to convert — surface them.
