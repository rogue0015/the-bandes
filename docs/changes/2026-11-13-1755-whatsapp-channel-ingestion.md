# 2026-11-13 17:55 — IT Opportunities Zim channel ingestion

- Added exact-title monitoring for the WhatsApp Channel `IT Opportunities Zim`.
- Added an administrator-only dashboard action to test up to the latest ten
  channel posts. Historical tests save records and schedule reminders but do
  not broadcast a backfill to the group.
- New channel posts are sent to Gemini with post text and supported image/PDF
  attachments (2 MiB per file); Gemini classifies and extracts structured
  opportunity/article data.
- New, non-duplicate opportunities are summarized to `The Bandeees`; articles
  are stored without sending group notifications. Channel posts are never
  replied to.
- Added stable WhatsApp channel/message references to deduplicate processing,
  configuration and operational documentation, and tests for media payloads,
  deduplication, reminder scheduling, and group notification behavior.

## Verification

- Backend and scraper tests: 21 passed.
- JavaScript syntax, Python compilation, and Docker Compose configuration
  checks passed.
- The real last-ten-post scan requires the administrator to start WhatsApp from
  the dashboard and run the test action while the channel is available.
