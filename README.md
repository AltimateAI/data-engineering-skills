# Data Engineering Skills

**Claude Code skills for Analytics & Data engineers working with dbt and Snowflake**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skills-blueviolet)](https://claude.ai/claude-code)

Altimate Data Skills is a collection of Claude Code skills that encode the workflows and best practices of experienced analytics engineers. These skills transform Claude from a code generator into a capable data engineering assistant.

## Key Results

- **53% accuracy** on [ADE-bench](https://github.com/dbt-labs/ade-bench) (43 real-world dbt tasks)
- **3x improvement** on model creation tasks vs baseline
- **84% pass rate** on Snowflake query optimization (62 TPC-H queries, 1TB dataset)
- **3.6x better performance** gains vs baseline (16.8% avg improvement vs 4.7%)
- **Airflow skills** (Claude Code, Sonnet 5.5 and Opus 5.5, 6 hard whole-project tasks, 3 runs each): on the 2 holdout cases pass rates went from 67% to 100% (Sonnet 5.5) and from 83% to 100% (Opus 5.5). Small sample and wide CIs; on common Airflow tasks (20-case core suite) both models are already near ceiling and the skills change little. See [Airflow Skills benchmark](#airflow-skills-1)
- Skills that teach Claude *how* to work, not just *what* to write

## Quick Start

```bash
/plugin marketplace add AltimateAI/data-engineering-skills
```

Install individual skill packs:
```bash
# Install dbt skills
/plugin install dbt-skills@data-engineering-skills

# Install Snowflake skills
/plugin install snowflake-skills@data-engineering-skills

# Install Airflow skills
/plugin install airflow-skills@data-engineering-skills

# Install altimate-code delegation skill
/plugin install altimate-code@data-engineering-skills
```

## Available Skills

### dbt Skills

| Skill | Purpose | Key Behaviors |
|-------|---------|---------------|
| **creating-dbt-models** | Model creation | Convention discovery → Write → Build → Verify output |
| **debugging-dbt-errors** | Error troubleshooting | Read full error → Check upstream → Apply fix → Rebuild |
| **testing-dbt-models** | Schema tests | Study existing test patterns → Match project style |
| **documenting-dbt-models** | Documentation | Analyze model → Generate descriptions |
| **migrating-sql-to-dbt** | Legacy SQL conversion | Parse SQL → Create proper dbt model |
| **refactoring-dbt-models** | Safe restructuring | Track dependencies → Apply changes → Verify downstream |
| **developing-incremental-models** | Incremental models | Strategy selection → unique_key design → Handle edge cases |

### Snowflake Skills

| Skill | Purpose | Key Behaviors |
|-------|---------|---------------|
| **finding-expensive-queries** | Cost analysis | Find and rank queries by cost/time/data scanned |
| **optimizing-query-by-id** | Performance tuning | Optimize using query ID from history |
| **optimizing-query-text** | Performance tuning | Profile query → Identify bottlenecks → Apply patterns |

### Airflow Skills

For Apache Airflow 2.x and 3.x projects. Each skill detects the project's Airflow version first and ships stdlib-only helper scripts (JSON output) that the agent runs to verify its work.

| Skill | Purpose | Key Behaviors |
|-------|---------|---------------|
| **authoring-airflow-dags** | Write, change and fix DAGs, including deferrable sensors and config-driven DAG factories | Detect version → Read existing DAGs → Write the period contract → Verify until clean → Execute with `airflow dags test`, then replay several runs (`replay_runs.py`) when state crosses runs. References: deferrable sensors and retry budgets, DAG factories |
| **migrating-to-airflow-3** | Port 2.x DAGs to 3.x | Inventory → Mechanical fixes → BEFORE/AFTER schedule preview must match → Fix runtime-only traps (`xcom_pull`, templates, manual-trigger intervals) → Replay BEFORE vs AFTER outputs on both versions (`replay_compare.py`) → Migration report |
| **testing-airflow-dags** | pytest suites for DAGs and custom operators | Offline `conftest.py` (no scheduler/connections) → Test each rule → Mutation check proves the suite catches bugs (`mutation_check.py`) → Replay multi-run state |

### altimate-code Delegation

| Skill | Purpose | Key Behaviors |
|-------|---------|---------------|
| **altimate-code** | Hand off data tasks to altimate-code | Verify install → Invoke `altimate-code run --yolo` non-interactively → Read output file → Summarize for user |

Use this skill when a task needs altimate-code's wired-up warehouse tools, column lineage, multi-step data exploration, or its 100+ specialized data tools.

**Requires altimate-code:** `npm install -g altimate-code` (Node 20+). Docs: [docs.altimate.sh](https://docs.altimate.sh) · Source: [AltimateAI/altimate-code](https://github.com/AltimateAI/altimate-code). The skill will detect a missing install and surface the exact command to the user.

## How Skills Work

Skills are markdown files that teach Claude **how to approach tasks**, not just what syntax to use. Each skill has two parts:

### 1. Trigger Conditions
When should this skill activate?

```yaml
---
name: creating-dbt-models
description: |
  Guide for creating dbt models. ALWAYS use this skill when:
  (1) Creating ANY new model (staging, intermediate, mart)
  (2) Task mentions "create", "build", "add" with model/table
  (3) Modifying model logic or columns
---
```

### 2. Workflow Instructions
What steps should Claude follow?

```markdown
# dbt Model Development

**Read before you write. Build after you write. Verify your output.**

## Critical Rules
1. ALWAYS run `dbt build` after creating models - compile is NOT enough
2. ALWAYS verify output after build using `dbt show`
3. If build fails 3+ times, stop and reassess your approach
...
```

## Usage Examples

Skills activate automatically based on your request:

| Your Request | Skill Activated |
|--------------|-----------------|
| "Create a new orders model" | `creating-dbt-models` |
| "Fix this compilation error" | `debugging-dbt-errors` |
| "Add tests to the customers model" | `testing-dbt-models` |
| "Document the revenue metrics" | `documenting-dbt-models` |
| "Create an incremental model for events" | `developing-incremental-models` |
| "This query is slow, optimize it" | `optimizing-query-text` |
| "Add a DAG that loads the vendor file every morning" | `authoring-airflow-dags` |
| "Get these DAGs working on Airflow 3" | `migrating-to-airflow-3` |
| "Make CI fail when a DAG doesn't import" | `testing-airflow-dags` |

## Combining with Altimate MCP Tools

Skills become even more powerful when combined with [Altimate's MCP server](https://docs.myaltimate.com/). The MCP server provides real-time access to your dbt project and data warehouse:

| MCP Tool | What It Provides |
|----------|------------------|
| `dbt_project_info` | Project structure, model list, sources |
| `dbt_model_details` | Column types, dependencies, compiled SQL |
| `dbt_compile` | Compile models without CLI |
| `snowflake_query_history` | Recent query executions and stats |
| `snowflake_table_stats` | Row counts, clustering info |

## Kits

Kits bundle skills, MCP servers, and instructions into a single activatable unit. Instead of installing skills one by one, activate a kit to get a complete development setup.

### Available Kits

| Kit | Description | Skills | MCP |
|-----|-------------|--------|-----|
| [dbt-snowflake](kits/dbt-snowflake/) | Complete dbt + Snowflake setup | 9 skills | dbt MCP server |

### Quick Start

```bash
# Install the kit
altimate-code kit install AltimateAI/data-engineering-skills

# Activate for your project
altimate-code kit activate dbt-snowflake

# Check what's active
altimate-code kit status
```

See [kits/README.md](kits/README.md) for the full kit format reference and how to create your own.

## Benchmark Results

Evaluated using [ADE-bench](https://github.com/dbt-labs/ade-bench), a framework for evaluating AI agents on analytics engineering tasks. All tests were run using Claude Sonnet 4.5.

### Overall Results

| Configuration | Accuracy | Tasks Resolved |
|---------------|----------|----------------|
| Baseline Claude (no skills) | 46.5% | 20/43 |
| Claude + Skills | **53.5%** | 23/43 |

### Results by Task Category

| Category | Baseline | With Skills | Improvement |
|----------|----------|-------------|-------------|
| Model Creation | 40% | 65% | **+25 pts** |
| Bug Fixing | 60% | 70% | +10 pts |
| Debugging | 35% | 50% | +15 pts |
| Refactoring | 30% | 35% | +5 pts |
| Analysis | 25% | 30% | +5 pts |

### Snowflake Query Optimization (TPC-H SF1000)

Benchmark on TPC-H 1TB dataset (62 queries) testing `optimizing-query-text` skill. All tests were run using Claude Sonnet 4.5.

| Configuration | Pass Rate | Avg Performance Improvement |
|---------------|-----------|----------------------------|
| Baseline Claude (no skills) | 77.4% (48/62) | 4.7% |
| Claude + Skills | **83.9% (52/62)** | **16.8%** (3.6x better) |

Skills provide structured optimization with query profiling, anti-pattern detection, and semantic preservation validation.

> **Note:** This benchmark uses our internal evaluation framework. We plan to open-source it soon with additional evals.

### Airflow Skills

Claude Code 2.1.286 with Claude Sonnet 5.5 and Claude Opus 5.5, every run graded by executing the agent's code in real Airflow 3.3.2 / 2.11.2 (DagBag import, `airflow dags test`, output data, schedule probes, planted-bug tests). Pass rate = all primary checks pass. The skills were frozen before the runs and iterated on dev cases only.

**Hard suite**: 6 whole-project tasks (migrations, deferrable sensors, a DAG factory), 3 runs per case, arms differ only by `skills/airflow/`. The cases were selected because a Sonnet 5.5 baseline failed them, so Sonnet's baseline is biased downward; Opus 5.5 was not used for selection. Only 2 of the 6 cases are holdout.

| Split | Model | Baseline | With skills | Paired delta [95% CI] |
|-------|-------|----------|-------------|-----------------------|
| Holdout (2 cases) | Opus 5.5 | 5/6 (83%) | **6/6 (100%)** | +0.17 [0.00, +0.33] |
| Holdout (2 cases) | Sonnet 5.5 | 4/6 (67%) | **6/6 (100%)** | +0.33 [0.00, +0.67] |
| Dev, tuned-on (4 cases) | Opus 5.5 | 9/12 (75%) | 12/12 (100%) | +0.25 [0.00, +0.50] |
| Dev, tuned-on (4 cases) | Sonnet 5.5 | 5/12 (42%) | 12/12 (100%) | +0.58 [+0.17, +1.00] |

**Core suite**: 20 common Airflow tasks (authoring, scheduling, migration, testing, debugging), 1 run per case. Both models are near ceiling without the skills, so there is little to gain.

| Model | Baseline | With skills | Paired delta [95% CI] |
|-------|----------|-------------|-----------------------|
| Opus 5.5 | 19/20 (95%) | 19/20 (95%) | 0.00 [-0.15, +0.15] |
| Sonnet 5.5 | 18/20 (90%) | 19/20 (95%) | +0.05 [0.00, +0.15] |

On older, weaker models the gains were larger: with altimate-code 0.12.2 on the core suite (older skill version, 3 runs per case), Sonnet 4.6 went from 30/60 to 54/60 and Haiku 4.5 from 18/60 to 36/60 (holdout for Haiku was flat). With 6 hard cases and 2 holdout cases the intervals are wide. Per-case results, cost, trigger rates, regressions and limitations: [evals/airflow/BENCHMARK.md](evals/airflow/BENCHMARK.md).

## Evals

The Airflow skills ship with an open eval suite: realistic tasks in [evals/airflow/cases](evals/airflow/cases) (20 core cases plus 6 `hard-*` cases), graded by running the agent's code against pinned Airflow 3.3 and 2.11 environments. Each case is run with and without the skills (baseline vs skill A/B) using the harness in [evals/harness](evals/harness/README.md). Results and method: [evals/airflow/BENCHMARK.md](evals/airflow/BENCHMARK.md).

```bash
evals/harness/setup_envs.sh                      # pinned grader + agent venvs (needs uv)
PY=~/.cache/des-evals/airflow-3.3/bin/python
$PY evals/harness/run_eval.py --cases evals/airflow/cases --self-test --split all   # validate graders, no LLM
for arm in baseline skill; do
  $PY evals/harness/run_eval.py --cases evals/airflow/cases --runner claude-code --arm $arm \
      --models claude-sonnet-5-5 --runs 3 --split all --out evals/airflow/results/my-$arm-run
done
# --runner altimate-code (default) uses your altimate-code provider auth instead
$PY evals/harness/report.py evals/airflow/results/my-baseline-run evals/airflow/results/my-skill-run --out evals/airflow/results/my-summary
```

`--runner claude-code` needs `CLAUDE_CODE_OAUTH_TOKEN` or `EVAL_CLAUDE_TOKEN_CMD`; see [CONTRIBUTING.md](CONTRIBUTING.md#airflow-evals).

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Ideas for contributions:
- New skills for workflows we haven't covered
- Improvements to existing skills based on your team's patterns
- Benchmark results on different datasets
- Bug reports and feature requests

## Roadmap

We're actively developing:
- **Cross-platform migration** — dbt to/from SQL Server, Oracle
- **Snowflake cost optimization** — Warehouse sizing, query patterns
- **Data quality workflows** — Anomaly detection, freshness checks

## Resources

- [Altimate MCP Server Docs](https://docs.myaltimate.com/)
- [ADE-bench Framework](https://github.com/dbt-labs/ade-bench)
- [dbt Slack Channel](https://getdbt.slack.com/archives/C05KPDGRMDW)
- [Contact Us](https://app.myaltimate.com/contactus)
## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

*Built by the team at [Altimate AI](https://altimate.ai/) — Making data engineering delightful.*
