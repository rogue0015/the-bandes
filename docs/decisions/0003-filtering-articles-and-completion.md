# Decision 0003: Filtering, article handling, and completion replies

## Context

Broad notifications without a configured recipient could be sent to the whole
WhatsApp group. Job matching also included non-entry IT roles and Project
Manager roles for Brandon. Link pages were all stored and scheduled as
opportunities, and there was no reminder schedule view.

## Decisions

- VacancyMail and VacancyBox listings are sent to Feli only when they are both
  IT-related and explicitly entry-level. Brandon receives Business Analyst or
  Business Analysis-related roles; Project Manager-only listings are excluded.
- Outbox notifications without a valid explicit recipient are skipped. A group
  broadcast must be deliberately enabled. Group-origin deadline reminders and
  relevance-filtered entrepreneurship notices may broadcast; scraper-job
  notifications and reminders must target the matched person.
- Link extraction classifies each page as an article or opportunity. Articles
  are summarized and stored without deadline reminders.
- Only an exact `Applied` or `Done` reply quoting the bot's opportunity summary
  can complete an opportunity. The URL in the quoted summary identifies the
  record; an unquoted status message cannot safely identify one.
- The dashboard lists reminder dates and delivery states. Completing an
  opportunity cancels its pending reminders and is reflected in the schedule.

## Consequences

- Existing pending outbox entries without recipients are marked skipped when
  claimed instead of being broadcast.
- If Feli or Brandon has no valid WhatsApp number configured, matching listings
  remain in the dashboard but are not sent as unaddressed group messages.
- Existing APIs and dashboard status filters continue to apply to opportunity
  records; article summaries are displayed separately by their record type.
