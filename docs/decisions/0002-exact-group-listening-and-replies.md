# Exact Group Listening and Replies

## Decision

- Match the configured WhatsApp group name exactly, ignoring case and Unicode
  normalization differences. The local configuration targets `The Bandeees`.
- Process group messages only when they contain at least one HTTP(S) link.
- Immediately acknowledge each link message, then fetch and parse its page,
  request structured opportunity fields through Gemini function calling, and
  save the result with 3-day and 1-day reminders when a deadline is present.
- Reply to the original message in the same group with registry status,
  extracted summary, deadline, and source URL after processing finishes.
- Use the existing local extraction as a fallback if Gemini is unavailable;
  never invent an unverified deadline.
- Do not automatically answer unrelated conversation, to avoid unsolicited
  noise in the group.
- Keep WhatsApp pairing under the Brandon dashboard's explicit start action.
  Persist the existing local WhatsApp session across Docker container rebuilds.
- Organize the dashboard into Setup, Data received, and Settings tabs; keep
  account password management in Settings.

## Rationale

Exact group matching avoids sending opportunity replies into similarly named
groups. The two-stage acknowledgement and extraction reply show progress
without turning the linked account into a general-purpose group responder.
Explicit pairing keeps account linking under the account owner's control.
