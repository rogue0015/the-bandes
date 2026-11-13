# Decision 0001: Application architecture

- **Date:** 2026-11-13
- **Status:** Accepted

## Context

The application needs a web dashboard, persistent opportunity tracking,
deadline reminders, WhatsApp group intake and delivery, and job scrapers that
can run independently of WhatsApp.

## Decision

- Use Python and FastAPI in `backend/` for the API, authentication, SQLite
  persistence, link processing, and persistent reminder state.
- Use a separate Node.js service in `WhatsApp/` with `whatsapp-web.js` for
  WhatsApp Web session management, group message intake, and outbound delivery.
- Run VacancyMail (Beautiful Soup) and VacancyBox (Selenium) collectors as an
  independently scheduled Python process in `scraper_service/`. Post results
  to the backend over an authenticated internal API.
- Serve a small same-origin dashboard from the FastAPI service to avoid
  unnecessary frontend build infrastructure for the MVP.
- Load bootstrap credentials and service secrets from the ignored local
  `.env`; hash user passwords before storing them.
- Isolate failures by processing one message/listing/reminder at a time and
  persisting work before attempting delivery.

## Consequences

- SQLite is suitable for a single-instance MVP; multi-instance deployments
  should migrate to a shared database and distributed job coordination.
- The WhatsApp service needs a linked WhatsApp Web session and may be affected
  by WhatsApp policy or client changes.
- Selenium requires a compatible browser and driver at runtime.
- Entrepreneurship sources remain configurable because no source list was
  specified.
