# Decision 0007: Render pairing QR during WhatsApp reconnection

**Date:** 2026-11-13

## Decision

Keep the administrator dashboard polling WhatsApp status while it is open,
including after the client first connects. When whatsapp-web.js reports
`LOGOUT`, let its in-progress page navigation perform the new pairing flow
instead of destroying and initializing the same client a second time. Show
the new QR as soon as the adapter emits it.

## Consequences

QR codes generated during reconnection become visible without a page reload or
manual restart. Avoiding a duplicate initialization also prevents competing
injection work on the same Chromium page. Non-logout disconnects continue to
use the existing bounded reconnect schedule.
