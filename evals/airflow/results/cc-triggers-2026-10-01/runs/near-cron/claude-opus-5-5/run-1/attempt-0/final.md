I added a cron job file to the repo, but it isn't running anywhere yet. It has to be copied to the Linux server first. I didn't add it to this Mac's crontab because it wouldn't do anything for the server.

**`deploy/cron.d/invoicer-cleanup`:**
```
0 2 * * * root /opt/invoicer/scripts/cleanup.sh >> /var/log/invoicer-cleanup.log 2>&1
```
- **When:** every night at 02:00, using the server's local timezone.
- **Logging:** standard output and errors are added to the end of `/var/log/invoicer-cleanup.log` on each run.

**To install it on the server:**
```
sudo install -m 0644 -o root -g root deploy/cron.d/invoicer-cleanup /etc/cron.d/
```
The cron service picks up files in `/etc/cron.d` automatically, so no restart is needed. I also added a short "Scheduled jobs" section to `README.md` with this command.

**Before you install, check these:**
- **Repo location:** I guessed the repo lives at `/opt/invoicer` on the server. If it's somewhere else, change the path in the file.
- **User:** the job runs as `root` so it can write to `/var/log` and delete files in `/var/lib/invoicer/reports`. If you have a dedicated `invoicer` user, use that instead. You'd then need to create the log file and give that user ownership of it.
- **Log contents:** `cleanup.sh` prints nothing when it succeeds, so the log will usually only show errors. If you want a record of each run, add a timestamp line to the script.

I haven't committed anything. Let me know if you'd like me to.