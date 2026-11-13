# 2026-11-13 19:18 — Root Dockerfile for Render Web Service

- Moved the backend image build definition to the repository root so a
  standard Render Docker Web Service can find `./Dockerfile`.
- Updated Docker Compose and the Render Blueprint to use the root Dockerfile.
- Documented manual Render Web Service settings; the standalone web service
  runs the dashboard/API, while WhatsApp and scraper need separate services.
- Validation: Render YAML parsed, Docker Compose configuration validated, and
  `git diff --check` passed.
