# 2026-11-13 17:37 — Strict routing and reminder tracking

- Tightened VacancyMail/VacancyBox matching: Feli requires an entry-level IT
  signal; Brandon matches Business Analyst/Business Analysis roles, not
  Project Manager-only roles.
- Prevented empty-recipient outbox items from broadcasting. The WhatsApp send
  endpoint now requires explicit recipients or an explicit broadcast request.
  Existing unscoped pending notifications are skipped.
- Routed scraper reminders to their matched recipient. Group-origin reminders
  and filtered entrepreneurship notices use explicit group broadcasts;
  unmatched managed-site reminders are skipped.
- Added article/opportunity page classification. Articles are summarized,
  stored as article records, and are not scheduled for deadline reminders.
- Added a reminder API and dashboard schedule. Quoted `Applied`/`Done` replies
  complete the opportunity and cancel pending reminders; unquoted messages are
  ignored.
- Updated the project plan and recorded decisions in
  `docs/decisions/0003-filtering-articles-and-completion.md`.

## Verification

- Backend and scraper tests: 17 passed.
- JavaScript syntax checks and `docker compose config --quiet`: passed.
- Rebuilt and started backend, WhatsApp, and scraper containers. Backend and
  WhatsApp health checks passed; WhatsApp remains idle until started from the
  administrator dashboard.
- The persisted database migration added article and explicit-broadcast
  fields. All 17 pending notifications without recipients were skipped; no
  pending reminders were present.
