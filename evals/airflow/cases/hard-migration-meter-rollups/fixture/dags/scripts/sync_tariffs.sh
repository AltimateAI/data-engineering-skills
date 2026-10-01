#!/usr/bin/env bash
# Day-ahead prices: the sync for {{ ds }} also refreshes {{ tomorrow_ds }}.
set -euo pipefail
dest="$PROJECT_ROOT/output/lake/tariffs"
mkdir -p "$dest"
for day in {{ ds }} {{ tomorrow_ds }}; do
  grep "^${day}," "$PROJECT_ROOT/data/tariffs.csv" > "$dest/${day}.csv"
done
echo "synced tariffs for {{ ds }} and {{ tomorrow_ds }}"
