#!/bin/bash
# Restore drill / disaster recovery on a clean machine (see docs/runbook.md, "Restore").
#
#   restore.sh <db-YYYYMMDD-HHMM.dump.gpg> <files-YYYYMMDD-HHMM.tar.gpg> <passphrase-file>
#
# Run it from the infra folder after `docker compose up -d db` on the new machine, with the
# Aadhaar keyring file restored from its offline recovery copy and LT_KEYRING_PATH pointing at it.
set -euo pipefail
DB_BACKUP=${1:?db backup file}
FILES_BACKUP=${2:?files backup file}
PASS=${3:?passphrase file}
COMPOSE="docker compose --env-file ../.env"

echo "1/5 checking the files decrypt"
gpg --batch --quiet --decrypt --passphrase-file "$PASS" "$DB_BACKUP" > /tmp/lt-restore.dump
gpg --batch --quiet --decrypt --passphrase-file "$PASS" "$FILES_BACKUP" > /tmp/lt-restore-files.tar

echo "2/5 restoring the database"
$COMPOSE exec -T db sh -c 'dropdb --if-exists -U loantracker loantracker && createdb -U loantracker loantracker'
$COMPOSE exec -T db pg_restore -U loantracker -d loantracker --no-owner < /tmp/lt-restore.dump

echo "3/5 restoring uploaded documents"
$COMPOSE run --rm -T --no-deps --entrypoint sh -v /tmp/lt-restore-files.tar:/restore.tar:ro api \
  -c 'cd /data && tar -xf /restore.tar'

echo "4/5 starting the app"
$COMPOSE up -d

echo "5/5 checking: ledger caches, daily log, and that Aadhaar numbers decrypt"
sleep 10
$COMPOSE exec -T api python -m app.cli rebuild-cache
$COMPOSE exec -T api python -m app.cli reconcile
$COMPOSE exec -T api python - <<'PY'
from sqlalchemy import select
from app.db import get_sessionmaker
from app.models import Borrower
from app.security import crypto
db = get_sessionmaker()()
rows = db.scalars(select(Borrower).where(Borrower.aadhaar_encrypted.is_not(None))).all()
ok = sum(1 for b in rows if crypto.decrypt(b.aadhaar_encrypted, crypto.AADHAAR)[-4:] == b.aadhaar_last4)
print(f"Aadhaar numbers that decrypt: {ok} of {len(rows)}")
raise SystemExit(0 if ok == len(rows) else 1)
PY
rm -f /tmp/lt-restore.dump /tmp/lt-restore-files.tar
echo "Restore finished. Record the date and result in docs/restore-drills.md."
