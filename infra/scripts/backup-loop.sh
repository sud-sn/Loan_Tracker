#!/bin/bash
# Runs inside the backup container: one backup a day at $BACKUP_AT (IST), forever.
set -u
export TZ=Asia/Kolkata
while true; do
  now=$(date +%s)
  target=$(date -d "today ${BACKUP_AT:-01:30}" +%s)
  if [ "$target" -le "$now" ]; then
    target=$(date -d "tomorrow ${BACKUP_AT:-01:30}" +%s)
  fi
  sleep $(( target - now ))
  /bin/bash /scripts/backup.sh || true
done
