# Contributing to Altimate Data Skills

Thanks for your interest in contributing! This document outlines how to get involved.

## Ways to Contribute

- **New Skills**: Create skills for workflows we haven't covered yet
- **Skill Improvements**: Enhance existing skills based on your team's patterns
- **Bug Reports**: Found an issue? Let us know
- **Documentation**: Help improve our docs

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Create a branch for your changes

## Skill Structure

Skills are markdown files with YAML frontmatter:

```markdown
---
name: skill-name
description: |
  When to use this skill
triggers:
  - keyword pattern
---

# Skill Title

Instructions for Claude...
```

Place new skills in the appropriate directory:
- `skills/dbt/` - dbt-related skills
- `skills/snowflake/` - Snowflake-related skills
- Create a new directory for other tools

## Submitting Changes

1. Make your changes in a feature branch
2. Test your skill with Claude Code
3. Submit a pull request with:
   - Clear description of changes
   - Any testing you performed
   - Screenshots or examples if applicable

## Skill Guidelines

Follow the official [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices).

When creating or modifying skills:

- **Be specific**: Clear trigger conditions prevent false activations
- **Include verification steps**: Always verify output, not just compilation
- **Add the 3-failure rule**: Stop and reassess after 3 failures
- **Match conventions**: Study the project before making changes
- **Test thoroughly**: Try your skill on real tasks

## Contributing Kits

Kits bundle skills, MCP servers, and instructions into shareable setups. To contribute a kit:

1. Create a directory under `kits/` with your kit name (e.g., `kits/my-kit/`)
2. Add a `KIT.yaml` file — see [kits/README.md](kits/README.md) for the format
3. Reference skills that exist in this repo or other public repos
4. Test with `altimate-code kit validate my-kit`
5. Submit a pull request following the template below

### Kit Guidelines

- **One kit per tool combination** (e.g., `dbt-snowflake`, not `dbt` and `snowflake` separately)
- **Include detection rules** so kits can be suggested automatically
- **Keep instructions concise** — focus on conventions, not tutorials
- **Set the correct tier** — use `community` for new contributions

## Questions?

- Open a GitHub issue for bugs or feature requests
- Join [dbt Slack #tools-altimate](https://getdbt.slack.com/) for discussions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
