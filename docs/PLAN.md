# Bandes Opportunities Assistant — Project Plan

## Goal

Build an application that collects opportunity links shared in the configured
WhatsApp group (`The Bandeees`), extracts useful details, sends a quick
summary, tracks deadlines, and sends reminders. A separate scraper service
collects relevant jobs and entrepreneurship opportunities from configured
websites.

## User-facing behavior

### WhatsApp link intake

1. Listen for new messages in the configured group, subject to a supported
   WhatsApp integration and the required group/member consent.
2. Detect links and avoid processing the same link repeatedly.
3. Fetch each linked page and classify it as an article or an opportunity.
   Summarize articles without treating them as opportunities. For opportunities,
   extract, where available:
   - title and organization
   - opportunity type and description
   - location and eligibility
   - application URL and deadline
4. Save the opportunity in a registry and send a concise summary as soon as
   practical. Clearly label fields that could not be verified and link to the
   original source.
5. Send reminders three days and one day before the deadline. Skip reminders
   for expired, withdrawn, or completed opportunities. A quoted `Applied` or
   `Done` reply to the bot's summary completes that opportunity and clears its
   pending reminders.

### Role-based job routing

The independent VacancyMail and VacancyBox scrapers should route only matching
jobs to the group:

- **Feli:** roles that are both IT-related and explicitly entry-level.
- **Brandon:** Business Analyst and Business Analysis-related roles only;
  Project Manager roles do not match.

The configured WhatsApp Channel `IT Opportunities Zim` is also monitored.
New posts are classified with Gemini; supported images and PDFs are attached
to the extraction request. The administrator can test up to the latest ten
posts from the dashboard. Historical test results are saved and scheduled
without sending a group notification; new opportunity posts are summarized to
The Bandeees.

Use configurable role criteria rather than relying only on titles. Include the
reason a job matched in its summary. Where the WhatsApp integration supports
reliable group mentions, tag the configured Feli or Brandon account; otherwise
send a clearly addressed message without pretending a mention occurred.

### Entrepreneurship opportunities

Find and track opportunities intended for innovators and developing leaders,
such as grants, competitions, incubators, fellowships, and leadership
programmes. Start with an explicitly configured source list; do not assume an
unverified source or scrape sites in ways their terms prohibit.

### Service controls

- The Brandon service-administrator account explicitly starts WhatsApp Web,
  checks its connection state, and scans the pairing QR from the dashboard.
  WhatsApp Web remains idle until he initiates it.
- The same account can add or remove public opportunity listing pages. The
  independent scraper reads this registry each cycle and records the last scan
  time for each configured page.

## Proposed components

1. **WhatsApp intake and delivery** — receives eligible group messages and
   sends summaries, job matches, and reminders.
2. **Link processor** — validates and fetches links, extracts structured
   details, and reports extraction failures without losing the original link.
3. **Opportunity registry** — stores source, extracted fields, category,
   matched recipient, status, timestamps, and reminder state; deduplicates
   records by canonical URL and, where useful, organization/title.
4. **Independent scraper service** — runs separately from WhatsApp intake:
   - `vacancymail.co.zw`: Beautiful Soup-based scraper.
   - `vacancybox.co.zw`: Selenium-based scraper for pages that need browser
     rendering.
   - Configured entrepreneurship sources: add an appropriate permitted
     extraction method per source.
5. **Matching and notification rules** — routes role matches to Feli or Brandon,
   and delivers relevant entrepreneurship opportunities to the configured
   audience.
6. **Reminder scheduler** — schedules three-day and one-day notifications
   using the opportunity deadline and configured timezone. Make delivery
   idempotent so retries do not create duplicate reminders, and expose the
   schedule in the dashboard.
7. **Configuration and operations** — keep credentials and group/account
   identifiers in environment configuration; log processing outcomes without
   logging secrets or unnecessary message contents.

## Suggested opportunity record

- Stable ID and canonical source URL
- Source type (group link, job scraper, or entrepreneurship source)
- Title, organization, description/summary, category, location, eligibility
- Application URL and parsed deadline, including timezone or date-only status
- Matched recipient(s) and match rationale
- First-seen and last-checked timestamps
- Status (new, active, expired, withdrawn, or completed)
- Reminder delivery state for the three-day and one-day reminders

## Delivery and reliability requirements

- Make scraping and link extraction resilient to timeouts, unavailable pages,
  changed layouts, and missing deadlines.
- Preserve the original URL and mark uncertain or absent details; never invent
  deadlines or eligibility.
- Respect source terms, robots guidance where applicable, rate limits, and
  reasonable request intervals. Use Selenium only where needed.
- Handle timezone and date-only deadlines consistently; do not send a reminder
  after a deadline has passed.
- Persist work before sending notifications, and track delivery attempts so
  failures can be retried safely.
- Provide operational logs and alerts for repeated scraper, extraction,
  scheduler, or WhatsApp delivery failures.

## Implementation phases

1. **Integration and requirements spike**
   - Verify whether the chosen supported WhatsApp integration can receive
     messages from the target group and send group messages/mentions.
   - Confirm consent, account setup, group identification, expected volume,
     timezone, hosting, and notification behavior.
   - If group listening is unsupported, agree on a supported alternative
     before implementation; do not depend on unofficial account automation.
2. **MVP registry and link workflow**
   - Define the data model and URL deduplication.
   - Implement link intake, extraction, immediate summaries, and failure
     reporting.
3. **Deadline reminders**
   - Add persistent scheduling for three-day and one-day reminders.
   - Test date boundaries, missing deadlines, retries, and duplicate delivery.
4. **Independent job scraper service**
   - Implement and test the VacancyMail Beautiful Soup scraper.
   - Implement and test the VacancyBox Selenium scraper.
   - Add Feli/Brandon matching, configurable criteria, and routed summaries.
5. **Entrepreneurship sources**
   - Agree on trusted, permitted sources and eligibility criteria.
   - Add source-specific collection and relevance rules.
6. **Hardening and launch**
   - Add monitoring, retention controls, deployment configuration, and
     operational documentation.
   - Pilot with a small set of links and verify summaries, routing, and
     reminders before enabling regular operation.

## Initial acceptance criteria

- A supported group message containing a new opportunity URL is processed once,
  stored, and followed by a summary with the source link.
- Missing or ambiguous details are identified as unknown rather than guessed.
- Active opportunities with known deadlines trigger one reminder three days
  before and one reminder one day before, in the configured timezone.
- Repeated links and scheduler retries do not create duplicate records or
  notifications.
- The two vacancy scrapers operate as an independent service and only deliver
  entry-level IT jobs to Feli and Business Analysis-related jobs to Brandon.
- Pages classified as articles are summarized and do not receive deadline
  reminders.
- A quoted `Applied` or `Done` reply to a bot summary completes only the linked
  opportunity; unrelated or unquoted status messages do not change records.
- Entrepreneurship opportunities come only from the agreed source list and
  meet the configured innovator/developing-leader criteria.
- Credentials are read from environment configuration and are never committed
  to source control.
