The cron job is defined in the repo and ready to install on the Linux host. I did not install it here because this machine is macOS, and I did not commit the changes.

**What I added**

- `deploy/invoicer-cleanup.cron`: an `/etc/cron.d` file that runs the cleanup script as root at 02:00 every night and appends stdout and stderr to `/var/log/invoicer-cleanup.log`. It sets an explicit PATH and empties MAILTO so cron does not email output.
- `deploy/install-cron.sh`: a root-only installer for Linux. It copies the cron file into `/etc/cron.d` with correct permissions, creates the log file, and adds a weekly logrotate rule so the log does not grow unbounded. It takes an optional install directory argument, defaulting to `/opt/invoicer`.
- README section describing the job and how to install and verify it.
- Made `scripts/cleanup.sh` executable, which cron requires.

**To activate on the server**, with the repo checked out at `/opt/invoicer`:

```bash
sudo deploy/install-cron.sh
```

One thing to check: the cron file assumes the server's local time zone. If the host runs in UTC and you want 2am local, add a `CRON_TZ=America/Los_Angeles` line to the cron file or adjust the hour.