# 0010 · Lighthouse and the PWA check

**Status:** accepted · PRD §15 acceptance check 13

Lighthouse 12 no longer has a PWA category. The check is: performance ≥ 90 and accessibility ≥ 90
on the mobile profile, plus an installability check (web manifest with icons, a service worker that
opens the app shell offline).

Measured on 5 Nov 2026 (Lighthouse 12.2.1, mobile, signed-in home page, invented data, served with
compression like Caddy): **accessibility 100, best practices 100, layout shift 0, performance
86–89**. The remaining gap is the time to the first list row on simulated slow 4G. To recheck on
the real install, run Lighthouse on the phone against the Tailscale address.
