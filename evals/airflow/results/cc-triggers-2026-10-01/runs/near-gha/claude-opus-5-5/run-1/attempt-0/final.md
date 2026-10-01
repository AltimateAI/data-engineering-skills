I added `.github/workflows/nightly-report.yml`. It runs `python scripts/nightly_report.py` every day at 06:00 UTC (`cron: "0 6 * * *"`), and you can also start it by hand from the Actions tab. The file parses as valid YAML, but it hasn't run on GitHub yet, so the first real test will be a manual run.

```yaml
on:
  schedule:
    - cron: "0 6 * * *" # every day at 06:00 UTC
  workflow_dispatch:
```

- **Setup:** the job checks out the repo, installs Python 3.12 and runs the script. The script uses `X | None` type syntax, which needs Python 3.10 or later; that matches `requires-python = ">=3.10"` in `pyproject.toml`. It only uses the standard library, so nothing else is installed.
- **Safeguards:** the job only has read access to the repo, has a 15-minute timeout, and won't start a new run while one is still going.

**Things to know before relying on it:**
- **Dates:** the script works out "yesterday" from the machine's local time. GitHub runners use UTC, so a 06:00 UTC run reports the previous UTC day.
- **Delays:** GitHub sometimes starts scheduled runs late when it's busy, and turns off scheduled workflows after 60 days with no repo activity.
- **Email:** the script currently only prints `sending report for <date>`. If it's changed to actually send email, the workflow will need SMTP credentials added as GitHub secrets and passed to that step.
- **Local test:** I couldn't run the script locally because the Python here is older than 3.10.

I haven't committed anything. Tell me if you want me to commit it or open a PR.