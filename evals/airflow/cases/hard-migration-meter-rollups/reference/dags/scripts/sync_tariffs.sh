#!/usr/bin/env bash
# Day-ahead prices: the sync for a day also refreshes the next day.
# Scheduled runs sync their interval's day; a CLI trigger (no logical date) syncs today.
{%- set day = ds if ds is defined else (dag_run.run_after | ds) %}
{%- set next_day = macros.ds_add(day, 1) %}
set -euo pipefail
dest="$PROJECT_ROOT/output/lake/tariffs"
mkdir -p "$dest"
for day in {{ day }} {{ next_day }}; do
  grep "^${day}," "$PROJECT_ROOT/data/tariffs.csv" > "$dest/${day}.csv"
done
echo "synced tariffs for {{ day }} and {{ next_day }}"
