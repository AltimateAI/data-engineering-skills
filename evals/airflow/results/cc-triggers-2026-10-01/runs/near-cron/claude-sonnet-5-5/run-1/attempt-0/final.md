This machine is macOS and `/var/log` and `/var/lib/invoicer` are Linux server paths, so I haven't installed anything here. Run this on the Linux host.

**Crontab entry** (edit with `crontab -e`, as a user that can write to the log):

```cron
0 2 * * * /opt/invoicer/scripts/cleanup.sh >> /var/log/invoicer-cleanup.log 2>&1
```

- Replace `/opt/invoicer` with wherever the repo is deployed. Cron needs the absolute path.
- `0 2 * * *` runs at 02:00 daily, in the server's timezone.
- `>> ... 2>&1` appends both stdout and stderr to the log.

**One-time setup** so the log is writable:

```bash
sudo touch /var/log/invoicer-cleanup.log
sudo chown <cron-user> /var/log/invoicer-cleanup.log
```

Use root's crontab (`sudo crontab -e`) instead if the user running it can't delete files in `/var/lib/invoicer/reports`.

**Optional logrotate config** at `/etc/logrotate.d/invoicer-cleanup`:

```
/var/log/invoicer-cleanup.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
```

**Check it:**
- `crontab -l` shows the entry.
- Run `/opt/invoicer/scripts/cleanup.sh` once by hand to confirm it works.

`cleanup.sh` only runs `find ... -delete` and prints nothing, so the log will stay empty unless something fails. To get a record of each run, change the cron line to this:

```cron
0 2 * * * (echo "[$(date -Is)] cleanup start"; /opt/invoicer/scripts/cleanup.sh; echo "[$(date -Is)] exit=$?") >> /var/log/invoicer-cleanup.log 2>&1
```

If you give me the deploy path and whether it should run as root or a service user, I can fill those in. I can also add an install script to the repo.