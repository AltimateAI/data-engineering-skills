#!/usr/bin/env bash
# parity_bench.sh — per-call Snowflake fallback for Phase 4 (parity) +
# Phase 5 (benchmark).
#
# Subcommands:
#   materialise <orig_sql> <opt_sql>
#       Creates `_SQO_ORIG_<run_id>` and `_SQO_OPT_<run_id>` as
#       TRANSIENT tables in $SQO_DEV_SCHEMA; writes a state file so
#       later subshells can find the names.
#   names
#       Prints the FQNs of the currently-materialised tables (reads
#       the state file). Use this in later shell invocations:
#         eval "$(scripts/parity_bench.sh names)"
#   bench <sql_file>
#       Runs <sql_file> against Snowflake with USE_CACHED_RESULT=FALSE
#       set in-session, so cold timings are honest across invocations.
#   cleanup
#       DROP IF EXISTS both tables, removes the state file.
#
# Environment:
#   SNOWFLAKE_RUN_SQL  Command that reads SQL on stdin and prints
#                      status to stderr (NOT stdout — we `eval` our
#                      stdout). Must be configured with the equivalent
#                      of snowsql's `-o exit_on_error=true`.
#   SQO_DEV_SCHEMA     REQUIRED (fail-closed). User-owned schema; the
#                      parity scratch tables materialise FULL result
#                      sets which may contain PII. Validated against
#                      a safe identifier regex.
#   SQO_STATE_DIR      Optional override for the state file location.
#                      Default: $(git rev-parse --git-dir)/skill/sqo/state

set -euo pipefail

: "${SNOWFLAKE_RUN_SQL:?SNOWFLAKE_RUN_SQL command required, e.g. snowsql -c myconn -o exit_on_error=true}"

# ---- State file ---------------------------------------------------
# Persist RUN_ID + table FQNs across subshell invocations.
_state_dir() {
  if [ -n "${SQO_STATE_DIR:-}" ]; then
    printf '%s\n' "$SQO_STATE_DIR"
  else
    local git_dir
    git_dir="$(git rev-parse --git-dir 2>/dev/null)" || { echo "parity_bench.sh: not inside a git repo and SQO_STATE_DIR unset" >&2; exit 1; }
    case "$git_dir" in
      /*) printf '%s\n' "$git_dir/skill/sqo" ;;
      *)  printf '%s\n' "$(pwd)/$git_dir/skill/sqo" ;;
    esac
  fi
}
_state_file() { printf '%s\n' "$(_state_dir)/state"; }

# ---- Identifier validation ----------------------------------------
# Accept quoted or unquoted Snowflake identifiers; refuse anything that
# could inject SQL or break the eval'd output. Covers `DEV_USER` and
# `MY_DB.DEV_USER` and the (optional) quoted forms.
_valid_ident() {
  # arg 1 = the string; return 0 if valid, 1 otherwise.
  printf '%s' "$1" | grep -qE '^([A-Za-z_][A-Za-z0-9_$]*|"[^"]+")(\.([A-Za-z_][A-Za-z0-9_$]*|"[^"]+"))?$'
}

# ---- Subcommand dispatch -------------------------------------------
cmd="${1:?materialise | names | bench | cleanup required}"
shift

case "$cmd" in
  materialise)
    ORIG_SQL="${1:?original SQL file required}"
    OPT_SQL="${2:?optimised SQL file required}"
    : "${SQO_DEV_SCHEMA:?SQO_DEV_SCHEMA required; use your own dev schema, never a shared one}"
    _valid_ident "$SQO_DEV_SCHEMA" \
      || { echo "parity_bench.sh: SQO_DEV_SCHEMA has an invalid identifier shape" >&2; exit 1; }

    [ -r "$ORIG_SQL" ] || { echo "parity_bench.sh: cannot read $ORIG_SQL" >&2; exit 1; }
    [ -r "$OPT_SQL"  ] || { echo "parity_bench.sh: cannot read $OPT_SQL"  >&2; exit 1; }

    # Shell-generated RUN_ID. Primary: uuidgen. Fallbacks must actually run.
    # The old pipeline `(uuidgen 2>/dev/null | tr | tr || date +%s%N)` masked
    # a missing uuidgen — the pipeline status came from `tr`, which is
    # always 0. Use an if/elif chain instead.
    RUN_ID=""
    if command -v uuidgen >/dev/null 2>&1; then
      RUN_ID="$(uuidgen | tr -d - | tr '[:lower:]' '[:upper:]')"
    elif command -v python3 >/dev/null 2>&1; then
      RUN_ID="$(python3 -c 'import uuid; print(uuid.uuid4().hex.upper())')"
    else
      # Last resort — on macOS `date +%s%N` leaves a literal 'N'; strip it.
      RUN_ID="$(date +%s)_$$"
    fi
    : "${RUN_ID:?RUN_ID generation failed}"

    ORIG_TABLE="${SQO_DEV_SCHEMA}._SQO_ORIG_${RUN_ID}"
    OPT_TABLE="${SQO_DEV_SCHEMA}._SQO_OPT_${RUN_ID}"

    # On INT/TERM/ERR during materialisation: drop any partials, then
    # exit with the right signal code. Each trap exits on its own —
    # the old handler just dropped and let the script keep going, which
    # printed the (just-dropped) table names on stdout and the caller
    # ran parity against gone tables.
    _drop_partials() {
      printf 'DROP TABLE IF EXISTS %s;\nDROP TABLE IF EXISTS %s;\n' \
        "$ORIG_TABLE" "$OPT_TABLE" | eval "$SNOWFLAKE_RUN_SQL" >/dev/null 2>&1 || true
    }
    trap '_drop_partials; exit 130' INT
    trap '_drop_partials; exit 143' TERM
    trap '_drop_partials; exit 1'   ERR

    # Materialise. $SNOWFLAKE_RUN_SQL writes banners / status to stdout;
    # redirect to stderr so our own stdout is clean for the caller's
    # `eval`. `pipefail` + `exit_on_error=true` on snowsql side ensure
    # SQL errors surface as a non-zero exit.
    {
      printf 'ALTER SESSION SET USE_CACHED_RESULT = FALSE;\n'
      printf 'CREATE OR REPLACE TRANSIENT TABLE %s AS\n' "$ORIG_TABLE"
      cat "$ORIG_SQL"
      printf '\n;\n'
      printf 'CREATE OR REPLACE TRANSIENT TABLE %s AS\n' "$OPT_TABLE"
      cat "$OPT_SQL"
      printf '\n;\n'
    } | eval "$SNOWFLAKE_RUN_SQL" >&2

    # Verify both tables actually exist. snowsql `exit_on_error` catches
    # most failures, but this is cheap belt-and-braces.
    probe_sql="
      SELECT COUNT(*) FROM ${SQO_DEV_SCHEMA}.INFORMATION_SCHEMA.TABLES
      WHERE TABLE_SCHEMA = UPPER(SPLIT_PART('${SQO_DEV_SCHEMA}', '.', 2))
        AND TABLE_NAME IN ('_SQO_ORIG_${RUN_ID}', '_SQO_OPT_${RUN_ID}');
    "
    # (We don't parse the count — relying on `exit_on_error` + the
    # earlier CREATEs having returned 0 is sufficient. The probe here
    # is for the operator's logs; stdout stays silent.)
    printf '%s' "$probe_sql" | eval "$SNOWFLAKE_RUN_SQL" >&2 || true

    # Clear traps now that we're committed.
    trap - INT TERM ERR

    # Persist state so later subshell invocations can find the tables.
    mkdir -p "$(_state_dir)"
    {
      printf 'export SQO_RUN_ID=%q\n'     "$RUN_ID"
      printf 'export SQO_ORIG_TABLE=%q\n' "$ORIG_TABLE"
      printf 'export SQO_OPT_TABLE=%q\n'  "$OPT_TABLE"
      printf 'export SQO_DEV_SCHEMA=%q\n' "$SQO_DEV_SCHEMA"
    } > "$(_state_file)"

    # Caller `eval`s our stdout — printf %q so quoted identifiers and
    # spaces survive. (Validated above, so this is defence-in-depth.)
    printf 'ORIG_TABLE=%q\nOPT_TABLE=%q\n' "$ORIG_TABLE" "$OPT_TABLE"
    cat >&2 <<EOF
parity_bench.sh: scratch tables materialised and recorded.
  Later subshells: eval "\$(scripts/parity_bench.sh names)"
  When done:       scripts/parity_bench.sh cleanup
EOF
    ;;

  names)
    sf="$(_state_file)"
    [ -f "$sf" ] || { echo "parity_bench.sh: no run in flight (state file $sf missing)" >&2; exit 1; }
    # shellcheck disable=SC1090
    source "$sf"
    : "${SQO_ORIG_TABLE:?state file missing SQO_ORIG_TABLE}"
    : "${SQO_OPT_TABLE:?state file missing SQO_OPT_TABLE}"
    printf 'ORIG_TABLE=%q\nOPT_TABLE=%q\n' "$SQO_ORIG_TABLE" "$SQO_OPT_TABLE"
    ;;

  bench)
    SQL_FILE="${1:?SQL file required}"
    [ -r "$SQL_FILE" ] || { echo "parity_bench.sh: cannot read $SQL_FILE" >&2; exit 1; }
    # Every bench call sets USE_CACHED_RESULT=FALSE in its own session —
    # per-call clients open fresh sessions and the materialise ALTER
    # doesn't survive. So we prepend it here.
    {
      printf 'ALTER SESSION SET USE_CACHED_RESULT = FALSE;\n'
      cat "$SQL_FILE"
    } | eval "$SNOWFLAKE_RUN_SQL"
    ;;

  cleanup)
    sf="$(_state_file)"
    if [ ! -f "$sf" ]; then
      echo "parity_bench.sh: cleanup: no state file ($sf) — nothing to drop" >&2
      exit 0
    fi
    # shellcheck disable=SC1090
    source "$sf"
    : "${SQO_ORIG_TABLE:?state file missing SQO_ORIG_TABLE}"
    : "${SQO_OPT_TABLE:?state file missing SQO_OPT_TABLE}"
    printf 'DROP TABLE IF EXISTS %s;\nDROP TABLE IF EXISTS %s;\n' \
      "$SQO_ORIG_TABLE" "$SQO_OPT_TABLE" | eval "$SNOWFLAKE_RUN_SQL" >&2
    rm -f "$sf"
    echo "parity_bench.sh: cleanup OK — dropped $SQO_ORIG_TABLE and $SQO_OPT_TABLE" >&2
    ;;

  *)
    echo "parity_bench.sh: usage: parity_bench.sh {materialise <orig> <opt> | names | bench <sql> | cleanup}" >&2
    exit 1
    ;;
esac
