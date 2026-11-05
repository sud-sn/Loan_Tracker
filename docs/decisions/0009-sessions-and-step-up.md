# 0009 · Sessions, step-up and alerts

**Status:** accepted · PRD §12

- Cookies: short access JWT (15 min), rotating refresh token (30 days, reuse ends the whole session
  family), double-submit CSRF token plus an Origin check on every write.
- Step-up (password again, and the authenticator code if on) lasts 5 minutes and is needed to reveal
  Aadhaar, reverse a payment, export data or reports, change roles, and turn off 2FA.
- Authenticator codes cannot be replayed. Lockout with back-off after 5 failures; rate limits on
  login, setup and step-up.
- The breached-password check uses a built-in list of common passwords and, optionally, an offline
  SHA-1 list (`LT_BREACHED_PASSWORDS_FILE`); nothing is sent online.
- Alerts: email only if SMTP is configured; the phone push carries counts only, never names or
  amounts, because it passes through Google's or Apple's servers.
