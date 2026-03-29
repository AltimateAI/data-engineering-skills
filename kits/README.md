# Kits

Kits bundle skills, MCP servers, and project-specific instructions into a single activatable unit. Instead of configuring skills one by one, activate a kit to get a complete development setup tailored to your stack.

## What's in a Kit?

A kit combines three things:

| Component | Purpose |
|-----------|---------|
| **Skills** | Claude Code skills that teach the agent how to perform specific workflows |
| **MCP Servers** | Tool servers that give Claude real-time access to your tools (dbt, Snowflake, etc.) |
| **Instructions** | Project conventions and best practices injected into every conversation |

## Available Kits

| Kit | Description | Skills | MCP |
|-----|-------------|--------|-----|
| [dbt-snowflake](dbt-snowflake/) | Complete dbt + Snowflake setup | 9 skills | dbt MCP server |

## Quick Start

```bash
# Install the kit from this repo
altimate-code kit install AltimateAI/data-engineering-skills

# Activate a kit for your project
altimate-code kit activate dbt-snowflake

# Check what's currently active
altimate-code kit status
```

## Auto-Detection

Kits can detect when they're relevant to your project. For example, the `dbt-snowflake` kit looks for `dbt_project.yml` in your workspace and prompts you to activate it automatically.

## Creating Your Own Kit

### 1. Create the directory

```
kits/
└── my-kit/
    └── KIT.yaml
```

### 2. Write KIT.yaml

```yaml
name: my-kit
description: One-line description of what this kit sets up
version: 1.0.0
author: Your Name
tier: community

skills:
  - source: "owner/repo"
    select:
      - skill-name-1
      - skill-name-2

mcp:
  tool-name:
    type: stdio
    command: ["uvx", "my-tool-mcp"]
    env:
      MY_VAR: "default-value"
    env_keys: ["MY_VAR"]
    description: "What this MCP server provides"

instructions: |
  Project conventions injected into every conversation.
  - Convention 1
  - Convention 2

detect:
  - files: ["config-file.yml"]
    message: "Detected my-tool project — activate my-kit?"
```

### 3. Validate and test

```bash
altimate-code kit validate my-kit
```

### 4. Submit a PR

See [CONTRIBUTING.md](../CONTRIBUTING.md) for submission guidelines.

## KIT.yaml Reference

### Top-Level Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Kit identifier (lowercase, hyphens) |
| `description` | Yes | One-line description |
| `version` | Yes | Semver version string |
| `author` | Yes | Author name or organization |
| `tier` | Yes | Trust tier: `built-in`, `verified`, or `community` |

### `skills`

Array of skill sources to install. Each entry has:

| Field | Description |
|-------|-------------|
| `source` | GitHub repo in `owner/repo` format |
| `select` | List of skill names to install from that repo |

### `mcp`

Map of MCP server configurations. Each entry has:

| Field | Description |
|-------|-------------|
| `type` | Server transport type (typically `stdio`) |
| `command` | Command and arguments to start the server |
| `env` | Default environment variables |
| `env_keys` | Environment variable names the user may need to configure |
| `description` | What the MCP server provides |

### `instructions`

Free-form text appended to Claude's context for every conversation in the project. Use this for team conventions, naming patterns, or workflow rules.

### `detect`

Array of auto-detection rules. Each entry has:

| Field | Description |
|-------|-------------|
| `files` | Glob patterns — if any match, the kit is suggested |
| `message` | Prompt shown to the user when files are detected |

## Trust Tiers

| Tier | Meaning | Who can publish |
|------|---------|-----------------|
| `built-in` | Ships with Altimate Code or this repo | Altimate AI |
| `verified` | Reviewed and approved by Altimate | Partner organizations |
| `community` | User-contributed, not reviewed | Anyone |

The tier is displayed when activating a kit so users can make informed trust decisions.

## Further Reading

- [Available skills](../skills/) in this repo
- [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines
- [Altimate MCP Server Docs](https://docs.myaltimate.com/) for MCP server details
