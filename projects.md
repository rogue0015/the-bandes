# Project decision announcement

**Decision recorded:** 2026-11-13 12:15 +02:00

Build the Bandes Opportunities Assistant as a modular application:

- A Python/FastAPI backend in `backend/` owns authentication, the opportunity
  registry, extraction, reminder scheduling, and the dashboard API.
- A separate `WhatsApp/` Node.js service uses `whatsapp-web.js` to listen for
  matching group links and deliver summaries, job matches, and reminders.
- A standalone Python `scraper_service/` collects VacancyMail and VacancyBox
  listings and submits them to the backend for matching and delivery.
- A lightweight web UI provides email/password login and opportunity
  management.

The two requested initial accounts will be provisioned from the local ignored
`.env` file and stored in the database with password hashes. The shared
bootstrap password is for initial access only and should be changed before
production use. WhatsApp integration requires an authenticated linked session
and remains subject to WhatsApp account policies and group consent.
