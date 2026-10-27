#!/usr/bin/env bash
# Smoke test: parity_bench.sh materialise / names / cleanup lifecycle
# with a mock SNOWFLAKE_RUN_SQL that prints banners on stdout.

set -u
cd "$(git rev-parse --show-toplevel)" 2>/dev/null || cd "$PWD"
script=skills/snowflake/snowflake-query-optimization/scripts/parity_bench.sh

td="$(mktemp -d)"
(
  cd "$td"
  git init -q 2>/dev/null
  cp "$OLDPWD/$script" ./parity_bench.sh
  mkdir -p scripts
  cp ./parity_bench.sh scripts/parity_bench.sh

  cat > /tmp/skill_test_mock_sql <<'MOCK'
#!/usr/bin/env bash
# Mock snowsql — prints banners to stdout and consumes stdin.
echo "SnowSQL version 1.3.1"
echo "Connecting as user='alice'..."
while IFS= read -r _; do :; done
echo "+---------------------+"
echo "| status              |"
echo "| Statement executed. |"
MOCK
  chmod +x /tmp/skill_test_mock_sql

  echo "SELECT 1" > orig.sql
  echo "SELECT 1 FROM dual" > opt.sql

  export SNOWFLAKE_RUN_SQL='/tmp/skill_test_mock_sql'
  export SQO_DEV_SCHEMA='DEV_ALICE'

  # 1) materialise prints ONLY ORIG_TABLE= and OPT_TABLE= on stdout
  out=$(./parity_bench.sh materialise orig.sql opt.sql 2>/dev/null)
  lc=$(printf '%s\n' "$out" | wc -l | tr -d ' ')
  if [ "$lc" != "2" ]; then
    echo "FAIL: materialise stdout has $lc lines, want 2"
    printf '%s\n' "$out"
    exit 1
  fi
  if ! printf '%s' "$out" | grep -q '^ORIG_TABLE='; then
    echo "FAIL: materialise stdout missing ORIG_TABLE="
    exit 1
  fi

  # 2) eval the captured stdout
  eval "$out"
  : "${ORIG_TABLE:?}"
  : "${OPT_TABLE:?}"

  # 3) names subcommand returns the same values from state
  out2=$(./parity_bench.sh names 2>/dev/null)
  if [ "$out2" != "$out" ]; then
    echo "FAIL: 'names' output differs from materialise output"
    printf 'materialise: %s\nnames: %s\n' "$out" "$out2"
    exit 1
  fi

  # 4) SQO_DEV_SCHEMA validation: invalid shape refused
  if SQO_DEV_SCHEMA='bad; echo pwned' ./parity_bench.sh materialise orig.sql opt.sql 2>/dev/null; then
    echo "FAIL: invalid SQO_DEV_SCHEMA was accepted"
    exit 1
  fi

  # 4b) Multi-line value refused — `printf | grep -qE` would accept
  #     if ANY line matched; the explicit newline-reject fixes that.
  if SQO_DEV_SCHEMA=$'DEV\nx; DROP ...; --' ./parity_bench.sh materialise orig.sql opt.sql 2>/dev/null; then
    echo "FAIL: multi-line SQO_DEV_SCHEMA was accepted"
    exit 1
  fi

  # 5) cleanup drops tables and removes state
  ./parity_bench.sh cleanup >/dev/null 2>&1 || { echo "FAIL: cleanup failed"; exit 1; }
  if ./parity_bench.sh names 2>/dev/null; then
    echo "FAIL: 'names' succeeded after cleanup"
    exit 1
  fi

  # 6) python3 uuid fallback is available
  python3 -c 'import uuid; print(uuid.uuid4().hex.upper())' >/dev/null \
    || { echo "FAIL: python uuid fallback"; exit 1; }

  rm -f /tmp/skill_test_mock_sql
  exit 0
)
rc=$?
rm -rf "$td"
if [ $rc -ne 0 ]; then
  echo "parity_bench_lifecycle: FAIL"
  exit 1
fi
echo "parity_bench_lifecycle: PASS"
