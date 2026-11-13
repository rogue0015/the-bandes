# 2026-11-13 18:12 — Render deployment and WhatsApp startup recovery

- Added guarded recovery for Chromium stale-profile-lock startup failures.
  Recovery removes only Chromium lock metadata, preserves session data, and
  refuses to clear a lock owned by a live local process.
- Recorded the lock-recovery behavior and its single-adapter assumption in
  decision 0006.
- Added the public `/keepalive` route and health pings to configured sibling
  services for free-tier wakeups.
- Added lightweight health endpoints to the scraper service and configured it
  to listen on Render's assigned port.
- Added a free-tier Render Blueprint and documented its ephemeral-storage,
  instance-hour, and Chromium resource limitations.
- Validation: three Node lock-recovery tests passed; JavaScript syntax,
  Python compilation, Render YAML parsing, and Docker Compose configuration
  checks passed. The rebuilt local backend and scraper health endpoints
  returned success, and keepalive probes were verified with unavailable peer
  services. The Python pytest suite could not run because pytest is not
  installed in the local Python environment.
