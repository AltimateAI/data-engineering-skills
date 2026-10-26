#!/usr/bin/env bash
# scripts/tests/run_all.sh — runs shellcheck + all smoke tests.

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
cd "$REPO_ROOT"

FAILS=()
PASSES=()

# ---- shellcheck ----------------------------------------------------
echo "===> shellcheck -x -S warning"
if command -v shellcheck >/dev/null 2>&1; then
  shell_scripts=$(find skills -type f -name '*.sh' -path '*/scripts/*' | sort)
  if [ -n "$shell_scripts" ]; then
    # shellcheck disable=SC2086
    sc_out=$(shellcheck -x -S warning $shell_scripts 2>&1 || true)
    if [ -z "$sc_out" ]; then
      PASSES+=("shellcheck")
      echo "  OK"
    else
      FAILS+=("shellcheck")
      echo "$sc_out"
    fi
  fi
else
  echo "  SKIP (shellcheck not installed; brew install shellcheck)"
fi

# ---- shell tests ---------------------------------------------------
for t in "$HERE"/test_*.sh; do
  [ -e "$t" ] || continue
  name="$(basename "$t")"
  echo "===> $name"
  for shell in bash zsh; do
    if command -v "$shell" >/dev/null 2>&1; then
      if "$shell" "$t" >/tmp/skill_test_out 2>&1; then
        PASSES+=("$name ($shell)")
        echo "  $shell: PASS"
      else
        FAILS+=("$name ($shell)")
        echo "  $shell: FAIL"
        sed 's/^/    /' /tmp/skill_test_out
      fi
    fi
  done
done

# ---- python tests --------------------------------------------------
for t in "$HERE"/test_*.py; do
  [ -e "$t" ] || continue
  name="$(basename "$t")"
  echo "===> $name"
  if python3 "$t" >/tmp/skill_test_out 2>&1; then
    PASSES+=("$name")
    echo "  PASS"
  else
    FAILS+=("$name")
    echo "  FAIL"
    sed 's/^/    /' /tmp/skill_test_out
  fi
done

echo ""
echo "===> Summary"
echo "  PASSES: ${#PASSES[@]}"
echo "  FAILS:  ${#FAILS[@]}"
if [ ${#FAILS[@]} -gt 0 ]; then
  printf '    %s\n' "${FAILS[@]}"
  exit 1
fi
