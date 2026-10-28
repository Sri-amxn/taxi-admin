# Verification performed

Tested on the supplied Apple Silicon Mac with Python 3.14.7 and Node 26.12.1. Setup instructions target Python 3.11+ and Node 22.12+; Windows instructions and launcher are supplied but were not executed on a Windows machine.

- Backend: **27 tests passed** against isolated in-memory SQLite databases.
- Backend tests cover missing/malformed/expired tokens, rider/driver access denial, demo isolation, missing live provider, stale-location availability, invalid revenue values, version conflicts, audit rollback, independent-session optimistic locking, idempotent settlement, historical split selection, paise rounding, zone validation, overlapping zones, global cap/disable, minimum fare, overnight schedule boundaries, pagination and invalid payloads.
- SQL Server: all admin table definitions compile with SQLAlchemy's MSSQL dialect. No live SQL Server credentials were available; actual ODBC connectivity, SQL Server transaction concurrency and shared migrations remain team integration checks.
- Alembic: initial schema upgraded successfully; `flask db check` reports no schema changes pending.
- Frontend: Vite production build passed. React Router's harmless `use client` bundle notices do not prevent the static client build.
- Dependency audit: npm install/audit reported **0 vulnerabilities** after updating Vite and React Router. Python dependencies are pinned with tested transitive constraints; this is not a full security audit.
- Swagger: `/api/docs/` and `/api/swagger.json` return HTTP 200; all 10 admin path patterns appear in the specification (13 method/path operations).
- Headless Chrome using the installed browser: entered demo, visited all six screens, saved/restored fare rules, calculated a ₹130 preview, created a disabled zone, saved/restored revenue percentages and expanded audit details. No JavaScript page errors were reported.
- Responsive browser check: 390px viewport had document width 390px, with no full-page horizontal overflow. Captured [desktop](dashboard-desktop.png) and [mobile](dashboard-mobile.png) screenshots.

The demo uses manual refresh and sample operations adapters. These checks do not claim that teammates’ unwritten modules, actual Google routes, payment/refund flows or live SQL Server integration have been tested.
