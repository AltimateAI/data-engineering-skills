#!/usr/bin/env bash
# Publish the per-carrier shipments report for one day.
# Usage: publish_shipments_report.sh YYYY-MM-DD
# Reads the vendor_shipments table (ship_date, carrier, weight_kg, ...) from
# warehouse/analytics.duckdb and writes reports/shipments_<day>.csv.
set -euo pipefail
DAY="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python "$ROOT/scripts/build_shipments_report.py" --warehouse "$ROOT/warehouse/analytics.duckdb" \
    --day "$DAY" --out "$ROOT/reports/shipments_${DAY}.csv"
