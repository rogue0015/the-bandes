# Render deployment

The root [Render Blueprint](../render.yaml) creates the backend, WhatsApp
adapter, and scraper as free web services for an experimental deployment.
The scraper has a small health endpoint so it can run as a Render web service
while continuing its independent background scan loop.

To create only the dashboard/API as a standard Render **Web Service**, connect
the repository and configure:

- Root Directory: repository root (leave blank or use `.`)
- Runtime: Docker
- Dockerfile Path: `./Dockerfile`
- Health Check Path: `/health`

The root Dockerfile builds the backend and serves the frontend dashboard. The
WhatsApp adapter and scraper still need their own services for the complete
application; use the Blueprint to create all three.

## Deploy

1. Push the project to a Git provider supported by Render and create a Blueprint
   using `render.yaml`.
2. In Render, set the requested values for both bootstrap passwords and
   `GEMINI_API_KEY`. Set the WhatsApp phone numbers if group mentions are
   needed. Do not copy secrets into the blueprint file.
3. Wait until all three services report healthy. The backend's public URL is
   also the dashboard URL. Sign in, start WhatsApp from the dashboard, and scan
   the QR code when asked.
4. Configure the external five-minute cron to make a `GET` request to
   `https://bandes-backend.onrender.com/keepalive`. The endpoint returns only
   `{"status":"ok"}` and also makes best-effort health requests to the WhatsApp
   and scraper services, so one cron target keeps all three free services
   active.

Render can take about a minute to wake a sleeping free service. The cron job
must continue to run; a single successful request does not keep a service
awake indefinitely.

## Free-tier limitations

This blueprint is experimental, not durable production hosting:

- Free services have ephemeral filesystems. The SQLite opportunity registry,
  Chromium/WhatsApp authentication profile, and local message queue can be lost
  when a service spins down, restarts, or redeploys. The keepalive ping can
  prevent idle spin-down while it is consistently succeeding, but cannot
  prevent platform restarts or preserve files.
- If WhatsApp's saved profile is lost, start WhatsApp from the dashboard and
  pair it again. A free deployment cannot attach the persistent disk needed to
  guarantee that the profile survives.
- Render's free instance-hour allowance is shared across the workspace. Keeping
  three free services continuously active consumes allowance much faster than
  keeping one service active; exceeding the allowance can suspend free
  services for the remainder of the month.
- Free instances have constrained CPU and memory. Chromium may be restarted
  under resource pressure.

For durable operation, use paid services with persistent storage or move the
registry and WhatsApp session to storage designed for persistence. The
five-minute keepalive endpoint is still available after upgrading, but paid
services do not need it to avoid free-tier idle spin-down.
