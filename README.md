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

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Ideas for contributions:
- New skills for workflows we haven't covered
- Improvements to existing skills based on your team's patterns
- Benchmark results on different datasets
- Bug reports and feature requests

## Roadmap

We're actively developing:
- **Airflow skills** — DAG development, debugging, testing
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
