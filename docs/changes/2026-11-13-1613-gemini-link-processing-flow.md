# 2026-11-13 16:13 — Gemini Link Processing Flow

- Send an immediate quoted acknowledgement for a link message in
  `The Bandeees`.
- Fetch and parse the linked page, then call Gemini's declared
  `extract_opportunity` function for title, organization, summary, category,
  location, eligibility, and deadline.
- Save the extracted opportunity and schedule reminders three days and one day
  before a known deadline.
- Send a quoted group reply after extraction with the saved summary and
  deadline; remove the duplicate generic group notification for this intake.
- Keep local parsing as a fallback when Gemini is unavailable and avoid
  responding to unrelated group messages.
- Added unit tests confirming Gemini function-call fields are used.
