# Runbook

Everything you need to install, update, roll back, back up, restore and rotate keys. Commands run
from the `infra/` folder unless noted.

## 1. Install (once)

### 1.1 The machine
- A computer that stays on (Linux, macOS, or Windows with WSL2), with **full-disk encryption** on
  (LUKS, FileVault or BitLocker), Docker and Docker Compose, and a UPS if you can.
- A **second drive** (USB disk or NAS) for daily backup copies, and a folder that syncs **off the
  machine** (another computer, or a cloud drive; the files are encrypted before they leave) for
  the weekly copy.

### 1.2 Private access with Tailscale
1. Install Tailscale on this machine and on your phone, and sign in to the same account.
2. In the Tailscale admin console, turn on **MagicDNS** and **HTTPS certificates**.
3. Note the machine's name (for example `loans.your-tailnet.ts.net`) and its Tailscale IP
   (`tailscale ip -4`).
4. **Do not forward any port on your router.** The app listens only on the Tailscale address.

### 1.3 Secrets and keys
```bash
sudo mkdir -p /srv/loantracker-keys && sudo chmod 700 /srv/loantracker-keys
cp ../.env.example ../.env && chmod 600 ../.env
# Fill in POSTGRES_PASSWORD, LT_SITE_ADDRESS, LT_APP_ORIGIN, LT_BIND_ADDRESS and the backup paths.
docker compose --env-file ../.env build
# A plain `docker run` (not the compose service), so Docker does not create a folder where the
# keyring file should be before it exists.
docker run --rm -u 0 -v /srv/loantracker-keys:/keys loantracker-api:local \
  python -m app.cli init-secrets --keyring /keys/aadhaar_keyring.json --env-file /keys/secrets.env
cat /srv/loantracker-keys/secrets.env >> ../.env     # the three LT_*_SECRET values
head -c 48 /dev/urandom | base64 > /srv/loantracker-keys/backup_passphrase
chmod 600 /srv/loantracker-keys/*
```
**Make an offline recovery copy** of `aadhaar_keyring.json`, `backup_passphrase` and `.env` (for
example on a USB stick kept in a safe place, or printed). Without the keyring, Aadhaar numbers
cannot be read. Without the passphrase, backups cannot be opened. Keep these copies **away from the
backups**.

### 1.4 Start
```bash
docker compose --env-file ../.env up -d
docker compose --env-file ../.env ps          # all services "running"/"healthy"
```
Open `https://loans.your-tailnet.ts.net` on the phone, create the owner account, then
**Settings → Cash balance** (start date and cash in hand), **Settings → Lender details**, and
**Settings → Authenticator app (2FA)**. Install it with **Add to Home screen**.

### 1.5 Health alert on the host
```bash
crontab -e
*/5 * * * * /path/to/infra/scripts/healthcheck.sh https://loans.your-tailnet.ts.net
```

## 2. Update
```bash
docker compose --env-file ../.env exec backup bash /scripts/backup.sh   # backup first, always
git pull
docker compose --env-file ../.env build && docker compose --env-file ../.env up -d
```
Migrations run automatically when the API starts. With images from CI, set
`LT_IMAGE_API=ghcr.io/<owner>/loantracker-api:<sha>` (and `LT_IMAGE_WEB`) in `.env`, then
`docker compose pull && docker compose up -d`.

## 3. Roll back (one step)
Set `LT_IMAGE_API` / `LT_IMAGE_WEB` back to the previous tag (or `git checkout <previous>` and
rebuild), then `docker compose up -d`. If the bad version ran a migration, restore last night's
backup instead (section 5). Migrations are versioned and each has a downgrade, but restoring is the
safe path with real money records.

## 4. Backups
- Nightly at `BACKUP_AT` (default 01:30 IST): an encrypted database dump and an encrypted tar of the
  documents go to the `backups` volume **and** the second drive. On Sundays they are also copied to
  the off-machine folder. 30 daily and 12 weekly copies are kept.
- Each dump is decrypted and read back (`pg_restore --list`) before it counts as good.
- `Settings → Backups and jobs` shows the last result. The nightly job alerts you (email or push, if
  set up) when a backup failed, is missing, or is more than 26 hours old.
- Backups never contain the Aadhaar master key.
- Manual backup: `docker compose --env-file ../.env exec backup bash /scripts/backup.sh`

## 5. Restore (and the quarterly restore drill)
Do this **before launch** and **every quarter**, on a clean machine or a spare VM, and write the
result in `docs/restore-drills.md`.
1. Install Docker, copy the repository and `.env`, and restore `aadhaar_keyring.json` and
   `backup_passphrase` **from the offline recovery copy** (not from the backups).
2. `docker compose --env-file ../.env up -d db`
3. `scripts/restore.sh /path/db-YYYYMMDD-HHMM.dump.gpg /path/files-YYYYMMDD-HHMM.tar.gpg /srv/loantracker-keys/backup_passphrase`
4. The script restores the database and documents, starts the app, rebuilds and checks the ledger
   caches, checks the daily log against the source tables, and confirms **every Aadhaar number
   decrypts**.
5. Open the app: check a few loans, payments, daily log days and documents against the notebook.

## 6. Rotate the Aadhaar master key
```bash
docker compose --env-file ../.env exec backup bash /scripts/backup.sh
docker compose --env-file ../.env run --rm api python -m app.cli rotate-key
```
The keyring file must be writable for this one command (mount it read-write temporarily). A new key
becomes active and every record's data key is re-wrapped; the record ciphertexts do not change. Keep
the old key in the keyring until the next verified backup and restore drill, then remove it. Update
the offline recovery copy.

## 7. Useful commands
```bash
docker compose --env-file ../.env logs -f api                    # JSON logs, personal data redacted
docker compose --env-file ../.env exec api python -m app.cli rebuild-cache   # recheck ledger caches
docker compose --env-file ../.env exec api python -m app.cli reconcile       # daily log vs. source tables
```

## 8. Test copy (invented data only)
```bash
cp ../.env ../.env.test   # change POSTGRES_PASSWORD, LT_SITE_ADDRESS and secrets; use NEW keys
docker compose -f docker-compose.yml -f docker-compose.test.yml -p loantracker-test --env-file ../.env.test up -d
docker compose -p loantracker-test exec api python -m app.cli seed-demo --borrowers 60
```
Never copy real borrower data into the test copy.

## 9. Check that it is private (acceptance check 18)
From a phone on mobile data **with Tailscale off**, open `https://loans.your-tailnet.ts.net`: it must
not load. Also run `nmap -Pn <your public IP>` from outside: no open ports. Turn Tailscale on: it
loads.
