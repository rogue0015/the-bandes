# Development Guide

1. Avoid monolithic code. Split features into focused, reusable modules with
   clear responsibilities.
2. Keep the interface professional and user-focused; do not add visible
   references to AI or AI-generated content.
3. Record architectural and product decisions in `docs/decisions/`. Record
   implementation changes in a timestamped entry under `docs/changes/`.
4. Follow established coding practices: validate inputs, handle errors
   explicitly, protect secrets, and add tests for important behavior.
5. Design for recovery. Isolate failures between services, persist work before
   sending notifications, make retries safe, and keep health/status visibility
   so recoverable errors do not stop the whole system.
