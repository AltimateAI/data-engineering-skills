I've added the cron job as a file in the repo, but it isn't running anywhere yet. This machine is macOS, not the Linux server, so I left the local crontab alone. You need to install the file on the server yourself.

**The job** (`deploy/cron/invoicer-cleanup`):
```
0 2 * * * root /opt/invoicer/scripts/cleanup.sh >> /var/log/invoicer-cleanup.log 2>&1
```
- It runs at 02:00 every day, in the server's local time zone.
- Both normal output and errors are added to the end of `/var/log/invoicer-cleanup.log`.
- It runs as `root`, because the script deletes files under `/var/lib/invoicer` and the log is in `/var/log`. If you have a dedicated `invoicer` user, use that instead and make sure it can write to the log file.

**To install it on the server** (I also added this to `README.md`):
```sh
sudo install -m 0644 -o root -g root deploy/cron/invoicer-cleanup /etc/cron.d/invoicer-cleanup
```
Cron loads files in `/etc/cron.d` automatically, so you don't need to restart anything.

**Before installing:**
- **Repo location:** the job assumes the repo is at `/opt/invoicer`, but nothing in the repo says where it's deployed. If it lives somewhere else, change the path in the cron file.
- **Log size:** the log file is never trimmed, so it will keep growing. You may want a logrotate rule for it.

Nothing is committed yet. Tell me if you want me to commit it.