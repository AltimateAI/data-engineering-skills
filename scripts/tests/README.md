# Smoke tests for skill scripts

Shell + Python unit tests for the `scripts/` directories bundled with
each skill. Keeps regressions caught locally — no CI required.

## Running

```bash
scripts/tests/run_all.sh
```

The runner:
- runs `shellcheck -x -S warning` across every `scripts/*.sh` in the
  repo. SC1091 ("can't follow source") is suppressed because it's a
  known shellcheck limitation for dynamically-sourced paths.
- runs each `scripts/tests/test_*.sh` in bash **and** zsh when both are
  available (zsh is the default Claude Code shell on macOS; several
  shell features behave differently there).
- runs each `scripts/tests/test_*.py` with python3.

Each test exits non-zero on failure; the runner aggregates and exits
non-zero if any test failed.

## Writing new tests

Follow the shape of the existing files. Each test:
- creates its own tempdir and `git init -q` inside it to avoid touching
  the main repo;
- copies the script-under-test from the skill's `scripts/` dir;
- exercises one specific scenario (empty state, missing input, failing
  dependency, nested dbt project, repo under a hidden parent, etc.);
- `echo FAIL …; exit 1` on failure; `echo PASS …; exit 0` otherwise.

Keep tests short. If a scenario needs a mock Snowflake / dbt binary,
put the mock in `scripts/tests/mocks/` and reference it from the test.
