#!/usr/bin/env bash
# Removes report files older than 14 days.
find /var/lib/invoicer/reports -type f -mtime +14 -delete
