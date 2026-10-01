This workspace is on macOS, and the job is meant for a Linux host, so I haven't installed anything. `scripts/cleanup.sh` exists and is executable. It deletes files older than 14 days under `/var/lib/invoicer/reports`.

**Option 1: root's crontab** (`sudo crontab -e`)

```cron
0 2 * * * /opt/invoicer/scripts/cleanup.sh >> /var/log/invoicer-cleanup.log 2>&1
```

**Option 2: `/etc/cron.d/invoicer-cleanup`** (this format needs a user field)

```cron
0 2 * * * root /opt/invoicer/scripts/cleanup.sh >> /var/log/invoicer-cleanup.log 2>&1
```

Setup on the Linux host:

1. Replace `/opt/invoicer` with the real checkout path. Cron needs an absolute path.
2. Create the log file if it doesn't exist: `sudo touch /var/log/invoicer-cleanup.log`. If the job runs as a non-root user, also `chown` the file to that user. Writing to `/var/log` normally needs root.
3. Check the schedule:
   - Run `sudo crontab -l` to list the job.
   - Run `sudo /opt/invoicer/scripts/cleanup.sh` once by hand.
4. Cron uses the server's timezone, so "2am" means 2am server time.

The script prints nothing on success, so the log will stay empty unless `find` errors. If you want a record of each run, change the script's `find` line to `find ... -print -delete`. Or add `echo "$(date -Is) cleanup done"` at the end. I can make that edit if you want it. A logrotate entry for the log file is also worth adding.

If you give me the deploy path and the user the job should run as, I can write the `/etc/cron.d` file into the repo.