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

Skills are markdown files with YAML frontmatter. Use only the fields defined by the [Agent Skills spec](https://agentskills.io/specification) so skills stay portable across Claude Code, claude.ai, the API and other agents (unknown keys such as `triggers:` are ignored by Claude Code and rejected by stricter loaders):

```markdown
---
name: skill-name            # required; must equal the directory name; lowercase, digits, hyphens; <= 64 chars
description: >-             # required; <= 1024 chars; this is the only text used to decide when to load the skill
  What the skill does and when to use it. Not for ... (use other-skill).
license: MIT                # optional
compatibility: Requires ... # optional; runtime requirements, <= 500 chars
metadata:                   # optional; string keys and string values
  version: "0.1.0"
---

# Skill Title

Instructions for Claude...
```

Quote or block-scalar (`>-`, `|`) any description that contains `: `; the frontmatter must parse as strict YAML.

Place new skills in the appropriate directory:
- `skills/dbt/` - dbt-related skills
- `skills/snowflake/` - Snowflake-related skills
- `skills/airflow/` - Apache Airflow skills
- Create a new directory for other tools

## Skill Structure and Evals

New skills follow the layout used by `skills/airflow/`:

```
skills/<tool>/<skill-name>/
├── SKILL.md        # workflow + gotchas; target < 300 lines (hard cap 500)
├── references/     # detail loaded on demand
└── scripts/        # deterministic checks the agent runs
```

- **SKILL.md** holds the workflow, defaults and gotchas. Every line should fix a failure observed in baseline runs; explain the why.
- **references/** files are linked from SKILL.md with an explicit read-when condition (e.g. "read `references/x.md` only if the project is on Airflow 2.x").
- **scripts/** are stdlib-only Python that print JSON to stdout and use exit codes, so they run in any project environment.
- **Shared files** (e.g. `skills/airflow/_shared/`) are vendored: each skill that uses one carries a byte-identical copy, because an installed skill can only read its own directory. Edit the canonical file, then re-copy it; `tests/skills/test_skill_spec.py` fails on any drift. `_shared` is never listed as a skill.

### Descriptions

- State what the skill does, then the triggers: realistic user phrasings and symptoms (error messages, "it processes the wrong day").
- End with `Not for ...` boundaries that name the neighbouring skill to use instead.
- Do not summarise the workflow in the description; the agent may act on the summary and skip the body.

### Evals

Skills that change agent behaviour need evals. Add cases under `evals/<tool>/cases/<case-id>/`:

- `case.yaml` - prompt, target version, split, limits
- `fixture/` - the project the agent starts from
- `reference/` (and optional `alt_reference/`) - a correct solution that must pass
- `mutants/` - plausible wrong solutions, each of which must fail at least one primary check
- `grade.py` - runs the agent's code and writes primary (behaviour) and secondary (process/style) checks

Before opening a PR:

1. Run the grader self-test (no LLM): `python evals/harness/run_eval.py --cases evals/<tool>/cases --self-test --split all`
2. Run the baseline and skill arms and compare them with `evals/harness/report.py`. See [evals/harness/README.md](evals/harness/README.md).
3. Run `pytest tests/` (spec lint, script tests, harness tests). CI runs the same checks.

### Airflow evals

The Airflow skills, cases and harness are the reference implementation of the above. Scope: changes
to `skills/airflow/`, `evals/airflow/` and `evals/harness/`. The harness itself is Airflow-specific
today (pinned venvs, grading helpers, trigger queries, macOS `sandbox-exec` isolation); another tool
needs its own cases and graders, and can reuse the run, report and sanitize logic.

**Environments.** `evals/harness/setup_envs.sh` (needs `uv`) creates four pinned venvs under
`${EVAL_ENV_ROOT:-~/.cache/des-evals}`: grader envs `airflow-3.3` (Airflow 3.3.2) and `airflow-2.11`
(Airflow 2.11.2), and separate agent envs `agent-airflow-3.3` / `agent-airflow-2.11` that the agent
works in. Graders never run in an agent env. Run the harness and the tests with the 3.3 grader
interpreter, which has pyyaml and pytest:

```bash
evals/harness/setup_envs.sh
PY=~/.cache/des-evals/airflow-3.3/bin/python
$PY evals/harness/run_eval.py --cases evals/airflow/cases --self-test --split all   # every case, no LLM
$PY -m pytest tests/ -m "not slow"
```

`--split all` matters: without it the self-test only covers the dev split, and holdout graders go
unchecked. Add `--parallel 4` to speed it up. The self-test runs every case's reference and
`alt_reference` (must pass), the untouched fixture and every mutant (must fail at least one primary
check). Save its output with `--out evals/airflow/results/selftest-final` after changing a grader.

**Runners and auth.**
- `--runner claude-code`: Claude Code on a subscription. Each attempt has a fresh config dir, so a
  logged-in `claude` is not used as is. Set `CLAUDE_CODE_OAUTH_TOKEN` (one token for the campaign,
  e.g. from `claude setup-token`) or `EVAL_CLAUDE_TOKEN_CMD`, a command that prints a current token
  (for example the token of your logged-in Claude Code, refreshed near expiry). The command runs
  before every attempt, so long campaigns survive token expiry. Never commit or log a token;
  `sanitize.py` redacts `sk-ant-*` tokens and every fetched token in result files.
- `--runner altimate-code` (default): uses the provider auth of your altimate-code install
  (`~/.local/share/altimate-code/auth.json`, plus `GOOGLE_APPLICATION_CREDENTIALS`,
  `GOOGLE_CLOUD_PROJECT` and `VERTEX_LOCATION` for Vertex models).

**Splits.** The skills are iterated on `dev` cases only. Do not read holdout prompts, fixtures or
graders while writing or changing a skill; report holdout and dev (tuned-on) separately.

**Hard cases** (`suite: hard`, ids `hard-*`) must be:
- **discriminating:** a current frontier model without the skills fails at least one of two probe
  runs for a genuine reason (read the transcript; a flaky grader, a killed run or an ambiguous
  prompt does not count). Cases the baseline solves are dropped, not made obscure.
- **probed and reviewed:** probe with at least two baseline runs, read the transcripts, and have a
  second reviewer (a person or another model) read the prompt, graders and mutants for fairness before
  the case is kept.
- **fair:** every primary check follows from the prompt and fixture as a senior engineer would read
  them. Each case ships a reference and an independently written `alt_reference` that pass, and
  mutants that fail, and the self-test must be clean. If a valid alternative solution fails a
  check, fix the check or state the requirement in the prompt (what, not how).

Selecting cases on one model's baseline failures biases that model's baseline downward; say which
model was used for selection when you report results.

## Submitting Changes

1. Make your changes in a feature branch
2. Test your skill with Claude Code and run the checks in [Skill Structure and Evals](#skill-structure-and-evals)
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
