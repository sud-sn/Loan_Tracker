#!/bin/bash
# A simple local check that tells the owner when the app is down (PRD section 13).
# Put it in cron on the host, every 5 minutes:
#   */5 * * * * /path/to/infra/scripts/healthcheck.sh https://loans.your-tailnet.ts.net
URL=${1:-https://localhost}
STATE=/tmp/loantracker-health
if curl -fsS --max-time 10 "$URL/readyz" > /dev/null; then
  [ -f "$STATE" ] && { rm -f "$STATE"; logger -t loantracker "app is back up"; }
  exit 0
fi
if [ ! -f "$STATE" ]; then
  touch "$STATE"
  logger -t loantracker "app is DOWN at $URL"
  # Optional: an email via the host's mail command, if one is set up.
  command -v mail > /dev/null && echo "Loan Tracker is not answering at $URL" | mail -s "Loan Tracker down" "${ALERT_EMAIL:-root}"
fi
exit 1
