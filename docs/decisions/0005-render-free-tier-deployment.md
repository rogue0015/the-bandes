# Decision 0005: Render free-tier deployment profile

**Date:** 2026-11-13

## Decision

Provide a Render Blueprint for an experimental free-tier deployment of the
backend, WhatsApp adapter, and scraper. Expose a minimal backend `/keepalive`
route for a five-minute external cron. The route also makes best-effort health
requests to the WhatsApp and scraper services so one scheduled request keeps
all three services warm.

## Consequences

Render free services do not provide persistent disks. SQLite data, the
WhatsApp browser profile, and the message queue can be lost on spin-down,
restart, or redeployment. The free-tier profile therefore is not suitable for
reliable production reminders or uninterrupted WhatsApp pairing. The Blueprint
and deployment notes make these limits explicit; durable operation requires
persistent storage and paid service plans.
