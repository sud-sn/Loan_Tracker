#!/bin/bash
# Nightly encrypted backup (PRD section 13).
#
# * database dump (pg_dump custom format) and a tar of the uploaded files, each encrypted with
#   AES-256 (gpg, passphrase from a file that is NOT stored with the backups)
# * written to the backups volume and copied to a second drive
# * on Sundays also copied to the off-machine folder (another computer or a synced cloud folder)
# * keeps 30 daily and 12 weekly copies
# * writes /backups/status.json, which Settings shows and the nightly job checks (a failed or
#   missing backup alerts the owner)
#
# The Aadhaar master key is never included: a stolen backup alone cannot reveal the numbers.
set -euo pipefail
export TZ=Asia/Kolkata
STAMP=$(date +%Y%m%d-%H%M)
DAILY=/backups/daily
WEEKLY=/backups/weekly
STATUS=/backups/status.json
mkdir -p "$DAILY" "$WEEKLY" /second-drive/loantracker
started=$(date -Iseconds)

fail() {
  printf '{"status":"failed","started_at":"%s","finished_at":"%s","detail":"%s"}\n' \
    "$started" "$(date -Iseconds)" "$1" > "$STATUS"
  exit 1
}
trap 'fail "backup step failed at line $LINENO"' ERR

encrypt() {
  gpg --batch --yes --quiet --symmetric --cipher-algo AES256 --passphrase-file "$BACKUP_PASSPHRASE_FILE" -o "$1"
}

DB_FILE="$DAILY/db-$STAMP.dump.gpg"
FILES_FILE="$DAILY/files-$STAMP.tar.gpg"
pg_dump --format=custom --no-owner | encrypt "$DB_FILE"
tar -C /data -cf - . | encrypt "$FILES_FILE"

# Prove the dump can be decrypted and read before calling it good.
gpg --batch --quiet --decrypt --passphrase-file "$BACKUP_PASSPHRASE_FILE" "$DB_FILE" | pg_restore --list > /dev/null

sha256sum "$DB_FILE" "$FILES_FILE" > "$DAILY/sha256-$STAMP.txt"
cp "$DB_FILE" "$FILES_FILE" "$DAILY/sha256-$STAMP.txt" /second-drive/loantracker/

if [ "$(date +%u)" = "7" ]; then
  cp "$DB_FILE" "$FILES_FILE" "$WEEKLY/"
  mkdir -p /offsite/loantracker
  cp "$DB_FILE" "$FILES_FILE" "$DAILY/sha256-$STAMP.txt" /offsite/loantracker/
fi

# Retention: 30 daily, 12 weekly (here and on the second drive).
ls -1t "$DAILY"/db-*.gpg 2>/dev/null | tail -n +31 | while read -r f; do s=${f##*/db-}; s=${s%.dump.gpg}; rm -f "$DAILY"/*"$s"*; done
ls -1t /second-drive/loantracker/db-*.gpg 2>/dev/null | tail -n +31 | while read -r f; do s=${f##*/db-}; s=${s%.dump.gpg}; rm -f /second-drive/loantracker/*"$s"*; done
ls -1t "$WEEKLY"/db-*.gpg 2>/dev/null | tail -n +13 | while read -r f; do s=${f##*/db-}; s=${s%.dump.gpg}; rm -f "$WEEKLY"/*"$s"*; done

size=$(du -sh "$DB_FILE" | cut -f1)
printf '{"status":"ok","started_at":"%s","finished_at":"%s","db_file":"%s","size":"%s"}\n' \
  "$started" "$(date -Iseconds)" "${DB_FILE##*/}" "$size" > "$STATUS"
echo "backup ok: $DB_FILE ($size)"
