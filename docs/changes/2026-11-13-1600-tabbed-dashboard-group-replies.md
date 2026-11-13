# 2026-11-13 16:00 — Tabbed Dashboard and Group Replies

- Added accessible Setup, Data received, and Settings tabs with keyboard
  navigation.
- Moved the opportunity registry into Data received and password management
  into Settings.
- Changed WhatsApp filtering from a broad regex to an exact, case-insensitive
  group name; set the local target to `The Bandeees`.
- Added quoted group replies for incoming link messages, including whether the
  opportunity was newly added, its details, deadline, and source.
- Routed the backend to the WhatsApp Compose service and mounted the existing
  local session directory to preserve pairing across container rebuilds.
- Updated setup documentation and added a summary formatting test.
