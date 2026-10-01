I added `.github/workflows/nightly-report.yml`. I haven't run it or committed it.

- **Triggers:** it runs on cron `0 6 * * *` (06:00 UTC daily) and on `workflow_dispatch` for manual runs.
- **Steps:** it checks out the repo, sets up Python 3.12 and runs `python scripts/nightly_report.py`. There is no install step because the script only uses the standard library.

- **Timezone:** `report_day()` uses `dt.datetime.now()`, which is naive local time. GitHub runners use UTC, so at 06:00 UTC it reports on the previous UTC day. If you expected a different timezone, that code needs changing.
- **Email:** the script currently only prints "sending report for …" and doesn't send anything. If the real version needs SMTP credentials, add them as repository secrets and pass them in an `env:` block on the run step.