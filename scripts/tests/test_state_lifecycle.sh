#!/usr/bin/env bash
# Smoke test: state.sh init / set / load / validate / reset lifecycle,
# across all three skills that ship state.sh.

set -u

for state_sh in \
  skills/snowflake/end-to-end-snowflake-pipeline/scripts/state.sh \
  skills/dbt/mssql-to-snowflake-dbt-migration/scripts/state.sh \
  skills/dbt/dbt-model-enhancement/scripts/state.sh ; do

  td="$(mktemp -d)"
  (
    cd "$td"
    git init -q 2>/dev/null
    cp "$OLDPWD/$state_sh" ./state.sh

    # 1) init
    source ./state.sh init >/dev/null 2>&1 || { echo "FAIL: init"; exit 1; }
    [ -n "${RUN_ID:-}" ] || { echo "FAIL: RUN_ID not set after init"; exit 1; }

    # 2) duplicate init without --force refuses
    if source ./state.sh init 2>/dev/null; then
      echo "FAIL: duplicate init without --force was allowed"; exit 1
    fi

    # 3) duplicate init with --force succeeds
    source ./state.sh init --force >/dev/null 2>&1 \
      || { echo "FAIL: init --force rejected"; exit 1; }

    # 4) set / load persists across subshells
    source ./state.sh set FOO 'hello world'
    source ./state.sh set BAR 'another'
    out=$(bash -c "source ./state.sh load; printf 'FOO=%s|BAR=%s' \"\$FOO\" \"\$BAR\"")
    if [ "$out" != "FOO=hello world|BAR=another" ]; then
      echo "FAIL: cross-shell load returned '$out'"; exit 1
    fi

    # 5) re-setting FOO strips the old line
    source ./state.sh set FOO 'again'
    out=$(bash -c "source ./state.sh load; printf '%s' \"\$FOO\"")
    [ "$out" = "again" ] || { echo "FAIL: FOO after re-set '$out'"; exit 1; }
    # ensure state file has exactly one FOO line
    foo_lines=$(grep -c '^export FOO=' "$STATE_FILE")
    [ "$foo_lines" = "1" ] || { echo "FAIL: $foo_lines lines of FOO in state"; exit 1; }

    # 6) validate: pass on present
    source ./state.sh validate FOO BAR >/dev/null 2>&1 \
      || { echo "FAIL: validate on present vars"; exit 1; }

    # 7) validate: fail on missing
    if source ./state.sh validate MISSING 2>/dev/null; then
      echo "FAIL: validate on missing var passed"; exit 1
    fi

    # 8) env vars are EXPORTED (child sees them)
    source ./state.sh load
    out=$(python3 -c 'import os; print(os.environ.get("FOO", "MISSING"))')
    [ "$out" = "again" ] || { echo "FAIL: python child saw FOO='$out'"; exit 1; }

    # 9) reset
    source ./state.sh reset >/dev/null 2>&1
    # Fresh load should fail now
    if source ./state.sh load 2>/dev/null; then
      echo "FAIL: load succeeded after reset"; exit 1
    fi

    exit 0
  )
  rc=$?
  rm -rf "$td"
  if [ $rc -ne 0 ]; then
    echo "state_lifecycle: FAIL for $state_sh"
    exit 1
  fi
done

echo "state_lifecycle: all three state.sh files PASS"
