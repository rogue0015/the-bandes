# Decision 0004: WhatsApp channel intake

## Context

The user requested adding the WhatsApp Channel `IT Opportunities Zim`, sending
its media to Gemini, testing its latest ten posts, and processing future posts.

## Decisions

- Monitor only the exact configured channel title. WhatsApp remains idle until
  the administrator starts it from the dashboard.
- Provide an administrator-only action to fetch and process up to the latest
  ten channel posts. Historical test posts do not send group notifications.
- Process new posts automatically. Save opportunities and schedule their
  reminders; send new opportunity summaries and reminders to `The Bandeees`.
- Send supported images (JPEG, PNG, WebP) and PDFs, up to 2 MiB each, as inline
  Gemini media inputs. Unsupported or oversized media returns a post-level
  error rather than being silently treated as processed.
- Persist a stable channel/message reference so retries and repeated tests do
  not create duplicate records or repeated Gemini calls.

## Consequences

- The account must already be subscribed to `IT Opportunities Zim` for it to
  appear to the WhatsApp Web client.
- Channel messages are never replied to. Summaries are sent only to
  `The Bandeees` for new, non-duplicate opportunity records.
- The test action intentionally transmits channel post text and supported media
  to the configured Gemini API.
