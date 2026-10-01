I added `.github/workflows/nightly-report.yml`. It runs `scripts/nightly_report.py` daily at 06:00 UTC (`cron: "0 6 * * *"`) and on manual dispatch. I haven't run it, so it's untested.

The job runs on `ubuntu-latest` with Python 3.12 and checks out the repo first. It installs nothing, because the script only imports the standard library and `pyproject.toml` has no runtime dependencies.

As written, the script only prints "sending report for …". It doesn't send any email yet, so the workflow won't send one either. If the script later needs SMTP credentials, you'll have to add them as repository secrets and pass them in through `env:`.

GitHub's scheduled runs can start a few minutes late, and they only fire from the default branch.