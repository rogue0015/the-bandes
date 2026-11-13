# Bandes Opportunities Assistant

An MVP for tracking opportunities shared in WhatsApp, matching jobs for Feli
and Brandon, and reminding the group about deadlines.

## Components

- `backend/`: FastAPI API, SQLite registry, login, link extraction, and reminder
  worker.
- `WhatsApp/`: `whatsapp-web.js` adapter for group intake and sending.
- `scraper_service/`: independent VacancyMail (Beautiful Soup), VacancyBox
  (Selenium), and configured entrepreneurship-source collector.
- `frontend/`: responsive same-origin login and opportunity dashboard.
- `docs/`: project plan, architecture decisions, and timestamped change records.

## Local setup

1. Copy `.env.example` to `.env`. Configure unique `APP_SECRET_KEY` and
   `INTERNAL_API_TOKEN` values, the initial users, exact WhatsApp group name, and the
   account phone numbers to mention. Use international digits without a leading
   `+` for `WHATSAPP_FELI_PHONE` and `WHATSAPP_BRANDON_PHONE`; these are required
   for actual WhatsApp mentions. The checked-in `.env` is ignored.
2. Install backend dependencies and start FastAPI:

   ```sh
   python -m venv .venv
   . .venv/bin/activate
   pip install -r backend/requirements.txt
   uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
   ```

3. In another terminal, install and start the WhatsApp adapter:

   ```sh
   cd WhatsApp
   npm install
   npm start
   ```

   Scan the displayed QR code with the WhatsApp account that is authorized to
   serve the group. The linked session is stored locally under
   `WhatsApp/.wwebjs_auth/` and is ignored by Git.

4. In a third terminal, install scraper dependencies and run the independent
   scraper process:

   ```sh
   pip install -r scraper_service/requirements.txt
   python scraper_service/main.py
   ```

   Selenium requires Chrome/Chromium and a compatible driver. Add only
   entrepreneurship listing URLs that you are authorized to collect to
   `ENTREPRENEURSHIP_SOURCES`.

5. Open `http://127.0.0.1:8000/` and sign in with a configured bootstrap user.

## Docker setup

Docker Compose runs the API/dashboard, WhatsApp adapter, and scraper as
separate services. SQLite data and the pending message queue use Docker
volumes; the WhatsApp browser session is kept in the ignored local
`WhatsApp/.wwebjs_auth/` directory so it survives container rebuilds.

1. Make sure `.env` is configured as described above. The default exact group
   name is `The Bandeees`; the additional monitored channel defaults to
   `IT Opportunities Zim`. Set `WHATSAPP_CHANNEL_NAME` to the exact channel
   title in WhatsApp. For actual WhatsApp mentions, set Feli's and Brandon's
   WhatsApp numbers.
2. Build and start all services:

   ```sh
   docker compose up --build -d
   docker compose ps
   ```

3. Open `http://127.0.0.1:8765/` and sign in with Brandon's account. In **Setup**,
   start WhatsApp Web and scan the QR if prompted. Add public opportunity
   listing pages there. Use **Test last 10 channel posts** to review recent
   channel items; that test sends supported images and PDFs to the configured
   Gemini API but does not broadcast historical test results. New channel
   opportunities are summarized to The Bandeees. In **Data received**, review
   tracked opportunities.
4. Configured websites are checked within about a minute after being added or
   manually queued, then every six hours. VacancyMail and VacancyBox are
   checked by the independent scraper service.

## Render deployment

The root `Dockerfile` builds the FastAPI/dashboard Web Service when deploying
the repository directly as a Render Web Service. Set the repository root as the
service's Root Directory and use `/health` as its health-check path. The root
`render.yaml` Blueprint provides an experimental free-tier deployment for all
three services.
See [Render deployment notes](docs/deployment-render.md) for setup, the
five-minute `/keepalive` cron URL, and the limitations of ephemeral SQLite and
WhatsApp session storage on free instances.

## Operations and limitations

- The first startup creates configured bootstrap users with PBKDF2 password
  hashes. Changing bootstrap credentials later does not reset existing users.
  Use the initially shared password only for local testing and rotate it with
  the dashboard's Change password control before production.
- Group listening and tagging depend on WhatsApp Web connectivity, exact
  configured group name, and actual group membership. Link messages in the
  configured group receive an opportunity summary reply; unrelated messages
  are not answered. WhatsApp Web automation may be affected by service policies
  or changes; use only with account authorization and group consent.
- `APP_COOKIE_SECURE=true` is required when serving over HTTPS. Put the API
  behind TLS and restrict service ports before deployment.
- The registry and reminder worker are single-instance SQLite MVP components.
  Use a shared database and distributed job coordination before scaling to
  multiple backend instances.
- Link extraction only fetches public HTTP(S) pages, limits response size, and
  treats deadlines as unknown when not verified. Gemini enhancement is
  optional and uses `GEMINI_API_KEY` when configured.
- The initial scrapers use general listing-page link extraction; website layout
  changes may require selector updates. Each source fails independently.
