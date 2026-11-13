# 2026-11-13 18:44 — Render QR codes during WhatsApp reconnection

- Keep dashboard WhatsApp status polling active for the whole administrator
  session, so QR codes emitted after a later disconnect are fetched and shown.
- For WhatsApp's `LOGOUT` disconnect reason, allow whatsapp-web.js to complete
  its current logout/navigation and emit a fresh pairing QR instead of
  overlapping it with another client initialization.
- Clear an obsolete QR when the WhatsApp service status request fails.
- Validation: frontend and adapter JavaScript syntax checks passed; the updated
  dashboard bundle was rebuilt and served locally.
