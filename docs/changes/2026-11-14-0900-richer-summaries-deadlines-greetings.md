# 2026-11-14 09:00 — Richer summaries, deadline following, and daily greetings

- Strengthened the Gemini extraction prompt so an opportunity summary must
  include a labelled description, requirements/qualifications, and the
  application deadline rather than a vague blurb.
- Added detail-link following to the link processor. When a page is an
  opportunity but no deadline is found, the extractor follows the most relevant
  "apply/details" links (up to three) and re-extracts until a deadline is found,
  keeping the original source URL as the record's source.
- Applied the same deadline-following to WhatsApp channel posts.
- Added a daily greetings service that schedules "Good morning my Queen Feli"
  at 07:00, "Good afternoon my Queen Feli" at 13:00, and "Good night my Queen
  Feli" at 21:00 in the configured timezone.
- Outbox notifications now accept an optional future `scheduled_at`; greetings
  are persisted with a per-day idempotency key so they are sent once and on
  time, and are skipped if the app starts after their time has passed.
- Wired greeting scheduling into the existing reminder loop.

## Verification

- Backend and scraper tests: 28 passed in a clean `python:3.12-slim` container.
