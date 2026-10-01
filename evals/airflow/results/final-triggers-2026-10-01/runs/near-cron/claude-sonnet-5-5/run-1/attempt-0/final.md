I haven't installed anything. This workstation is macOS, and the job belongs on the Linux host that runs invoicer. `scripts/cleanup.sh` is executable and only deletes report files older than 14 days under `/var/lib/invoicer/reports`, so it's safe to schedule as is.

**Option A: root's crontab** (`sudo crontab -e`)

```cron
0 2 * * * /opt/invoicer/scripts/cleanup.sh >> /var/log/invoicer-cleanup.log 2>&1
```

**Option B: system cron file** at `/etc/cron.d/invoicer-cleanup`. This one needs a user field, and the file must be owned by root with mode 0644:

```cron
0 2 * * * root /opt/invoicer/scripts/cleanup.sh >> /var/log/invoicer-cleanup.log 2>&1
```

Before using either one:
- **Path:** Replace `/opt/invoicer` with wherever the repo is deployed. Cron needs an absolute path.
- **Log file:** Writing to `/var/log` requires root, which is why both options run as root. To run as a service user instead, create the log first with `sudo touch /var/log/invoicer-cleanup.log && sudo chown <user> /var/log/invoicer-cleanup.log`.
- **Timezone:** Cron uses the server's local time zone. Check it with `timedatectl`.
- **Log growth:** The log is appended to forever. A logrotate config at `/etc/logrotate.d/invoicer-cleanup` handles this:
  ```
  /var/log/invoicer-cleanup.log {
      weekly
      rotate 8
      compress
      missingok
      notifempty
  }
  ```
- **Empty log:** The script prints nothing when it succeeds, so the log will be empty on a normal night. If you want a record of each run, wrap it like this:
  ```cron
  0 2 * * * root { date -Is; /opt/invoicer/scripts/cleanup.sh; echo "exit=$?"; } >> /var/log/invoicer-cleanup.log 2>&1
  ```

I can add the cron file and logrotate config to the repo (for example under `deploy/`) if you give me the deploy path and the user to run it as.