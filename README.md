# Altimate Data Skills

**Claude Code skills for analytics engineers working with dbt and Snowflake**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skills-blueviolet)](https://claude.ai/claude-code)

Altimate Data Skills is a collection of Claude Code skills that encode the workflows and best practices of experienced analytics engineers. These skills transform Claude from a code generator into a capable data engineering assistant.

## Key Results

- **53% accuracy** on [ADE-bench](https://github.com/dbt-labs/ade-bench) (43 real-world dbt tasks)
- **3x improvement** on model creation tasks vs baseline
- Skills that teach Claude *how* to work, not just *what* to write

## Quick Start

```bash
# Install from marketplace (coming soon)
/plugin marketplace add AltimateAI/altimate-skills

# Or clone and install manually
git clone https://github.com/AltimateAI/altimate-skills.git
cp -r altimate-skills/skills ~/.claude/skills/
```

Verify installation:
```bash
/skills list
```

## Available Skills

### dbt Skills

| Skill | Purpose | Key Behaviors |
|-------|---------|---------------|
| **dbt-dev** | Model creation | Convention discovery → Write → Build → Verify output |
| **dbt-debug** | Error troubleshooting | Read full error → Check upstream → Apply fix → Rebuild |
| **dbt-testing** | Schema tests | Study existing test patterns → Match project style |
| **dbt-document** | Documentation | Analyze model → Generate descriptions |
| **dbt-sql-to-model** | Legacy SQL conversion | Parse SQL → Create proper dbt model |
| **dbt-refactor** | Safe restructuring | Track dependencies → Apply changes → Verify downstream |

### Snowflake Skills

| Skill | Purpose | Key Behaviors |
|-------|---------|---------------|
| **snowflake-query-optimization** | Performance tuning | Profile query → Identify bottlenecks → Apply patterns |

## How Skills Work

Skills are markdown files that teach Claude **how to approach tasks**, not just what syntax to use. Each skill has two parts:

### 1. Trigger Conditions
When should this skill activate?

```yaml
---
name: dbt-dev
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
| "Create a new orders model" | `dbt-dev` |
| "Fix this compilation error" | `dbt-debug` |
| "Add tests to the customers model" | `dbt-testing` |
| "Document the revenue metrics" | `dbt-document` |
| "This query is slow, optimize it" | `snowflake-query-optimization` |

## Combining with Altimate MCP Tools

Skills become even more powerful when combined with [Altimate's MCP server](https://docs.myaltimate.com/). The MCP server provides real-time access to your dbt project and data warehouse:

| MCP Tool | What It Provides |
|----------|------------------|
| `dbt_project_info` | Project structure, model list, sources |
| `dbt_model_details` | Column types, dependencies, compiled SQL |
| `dbt_compile` | Compile models without CLI |
| `snowflake_query_history` | Recent query executions and stats |
| `snowflake_table_stats` | Row counts, clustering info |

## Benchmark Results

Evaluated using [ADE-bench](https://github.com/dbt-labs/ade-bench), a framework for evaluating AI agents on analytics engineering tasks.

### Overall Results

| Configuration | Accuracy | Tasks Resolved |
|---------------|----------|----------------|
| Baseline Claude (no skills, no MCP) | 46.5% | 20/43 |
| Claude + Skills + MCP | **53.5%** | 23/43 |

### Results by Task Category

| Category | Baseline | With Skills | Improvement |
|----------|----------|-------------|-------------|
| Model Creation | 40% | 65% | **+25 pts** |
| Bug Fixing | 60% | 70% | +10 pts |
| Debugging | 35% | 50% | +15 pts |
| Refactoring | 30% | 35% | +5 pts |
| Analysis | 25% | 30% | +5 pts |

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
- [dbt Slack #tools-altimate](https://getdbt.slack.com/)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

*Built by the team at [Altimate AI](https://altimate.ai/) — Making data engineering delightful.*
