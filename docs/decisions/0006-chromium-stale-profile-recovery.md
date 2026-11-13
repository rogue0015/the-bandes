# Decision 0006: Recover stale Chromium profile locks

**Date:** 2026-11-13

## Decision

When WhatsApp initialization fails specifically because Chromium reports a
profile singleton lock, retry initialization once after removing only the
profile's lock metadata. Preserve all browser authentication and profile data.
Do not remove the lock when its local owner PID is still an active Chromium
process. Surface a second failure through the existing WhatsApp error state and
reconnect handling.

## Consequences

This recovers profile locks left behind by a replaced container or crashed
browser without resetting WhatsApp pairing. It assumes only one active
WhatsApp adapter uses a profile directory at a time; do not share that profile
between replicas.
