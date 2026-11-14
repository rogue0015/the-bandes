# Decision 0008: Deadline discovery and daily greetings

## Context

The user was not satisfied with the generated opportunity summaries and job
descriptions. They asked that summaries always cover the job description, the
requirements, and the deadline; that the extractor follow a "more details" link
when the deadline is not on the shared page until it is found; and that
Feli receive three daily greetings at 07:00, 13:00, and 21:00.

## Decisions

- Opportunity summaries produced for the tracker must include a labelled
  description, the key requirements/qualifications, and the deadline. The
  summary is the primary human-facing artifact, so it must be self-contained.
- When a page is classified as an opportunity but no deadline is found, the
  extractor follows the most relevant detail/application links (bounded to
  three) and re-extracts until a deadline is found. The original post URL is
  kept as the record's source so links and deduplication stay stable.
- Daily greetings are scheduled through the existing notification outbox using
  a per-day idempotency key, so a greeting is sent at most once per day and only
  when its time is still ahead. Greetings are skipped if the service starts
  after their time has passed, avoiding late "good morning" messages.

## Consequences

- Summary generation may make an additional Gemini call per followed link; the
  follow count is bounded to keep latency and cost predictable.
- Deadline following performs extra outbound fetches only for opportunity pages
  that are missing a deadline, and only for links that look like application or
  detail pages.
- Greetings require `WHATSAPP_FELI_PHONE` to be configured; otherwise they are
  silently skipped, consistent with the existing recipient rules.
