# WhatsApp pairing and managed sources

- **Timestamp:** 2026-11-13 15:25 +02:00
- Added Brandon-only dashboard controls to explicitly start WhatsApp Web and
  display its pairing QR and connection state.
- Changed the WhatsApp adapter to remain idle until the authorized dashboard
  user starts it; QR generation and service endpoints are protected by the
  internal service token.
- Added a Brandon-only website registry UI and persistent API for adding and
  removing public opportunity listing pages.
- Updated the independent scraper to read managed pages, process listing links,
  submit new opportunities, and record scan timestamps.
- Running the dashboard in Docker while using the locally installed Chrome
  WhatsApp client; the app's public port remains localhost-only.
