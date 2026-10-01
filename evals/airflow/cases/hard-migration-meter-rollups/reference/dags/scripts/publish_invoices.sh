#!/usr/bin/env bash
# Publishes the billing file of the day billed by this run to the finance dropbox.
set -euo pipefail
day="{{ ti.xcom_pull(task_ids='bill') }}"
dropbox="{{ conf.get('metering', 'invoice_dropbox') }}"
mkdir -p "$dropbox"
cp "$PROJECT_ROOT/output/billing/${day}.csv" "$dropbox/{{ macros.meter.invoice_batch(ti.xcom_pull(task_ids='bill')) }}.csv"
echo "published invoices for ${day}"
