I added the cron job as a file in the repo, but it isn't running anywhere yet. This machine is macOS, so installing it here wouldn't give you a job on the Linux host. Someone needs to copy it onto the server.

**New file: `deploy/cron/invoicer-cleanup`**, written for `/etc/cron.d/`:

```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

0 2 * * * root /opt/invoicer/scripts/cleanup.sh >> /var/log/invoicer-cleanup.log 2>&1
```

- **Schedule:** it runs every day at 02:00 in the server's local time zone.
- **Logging:** both normal output and errors are added to the end of `/var/log/invoicer-cleanup.log`.
- **README:** I added a short "Scheduled jobs" section with the install command.

**To install on the Linux host:**
```sh
sudo install -m 0644 deploy/cron/invoicer-cleanup /etc/cron.d/invoicer-cleanup
```

**Two choices to confirm before installing:**
- **Install path:** I assumed the repo lives at `/opt/invoicer`. If it's somewhere else, change the script path in the file.
- **Runs as root:** a normal user usually can't write to `/var/log` or delete files in `/var/lib/invoicer/reports`. If you'd rather use a dedicated `invoicer` user, give that user write access to the log file and change `root` to `invoicer` in the file.

The changes aren't committed yet.