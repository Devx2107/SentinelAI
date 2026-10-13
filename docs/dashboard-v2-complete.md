# Dashboard v2 implementation

The completed software lives on `feature/dashboard-v2-complete` in the
isolated dashboard checkout. Earlier main-checkout reliability changes are
preserved. The user's request to finish the software supersedes the original
phase-by-phase pause; the Phase 1 commit remains intact beneath this work.

## Features

- Responsive control room: desktop sidebar and mobile bottom navigation.
- Overview: 24-hour counts, device status, severity chart, expiring access window
  and latest activity.
- Events: URL-synced filters, literal message search, datetime ranges, expandable
  rows, keyset pagination, live toggle, deduplication and CSV export of loaded
  rows (1,000-row cap, formula-prefix protection).
- Devices: effective online/stale/offline status, last seen, capabilities and
  per-device activity.
- Access: create/edit card label and notes; confirmed enable/disable actions;
  optimistic toggles with error rollback; live authorization countdown.
- Entry monitor: 24-hour/7-day series, confidence histogram, average confidence
  and accessible chart data tables. Authenticated entry events are included.
- System: mode, uptime, database counts/size, MQTT connectivity and startup
  readiness. No full filesystem paths or credentials in responses.
- Resumable authenticated fetch streams: event IDs, reconnect backoff, polling
  after three failures, ten-stream limit, connection cleanup and critical-event
  announcements. A demo producer belongs to app lifetime.
- Same-origin JSON writes, request limits, constant-time Basic auth, bounded
  write rate limits, no-store API responses and UI security headers.
- Prebuilt assets and a shared demo/live launcher with a separate runtime
  database. Existing dashboard v1 remains available in live mode.

## Run and maintain

See [RPI_START.md](RPI_START.md) for the laptop preview and Pi handoff.
Frontend development uses Node 22.21+:

```bash
cd dashboard-ui
npm ci
npm run dev
npm test
npm run build
```

Run the demo API in another terminal. Vite proxies `/api` to port 5001. Build
output goes to `hub/static/dashboard` and is committed for the Pi.

Backend tests: `.venv/bin/python -m pytest -q` (Windows:
`.\.venv\Scripts\python -m pytest -q`). To regenerate shared fixtures:
`python hub/tools/export_dashboard_contract.py`. Python contract tests and
TypeScript runtime guards share the schema in `dashboard-ui/src/api/schema`.

Add a page in `dashboard-ui/src/pages.tsx`, register its route/navigation in
`main.tsx`, define its API types and response schema, then add behavior tests.
For a backend endpoint, put pure query/aggregation logic in `hub/services` and
keep Flask transport in `hub/api`. Never import hardware from demo services.

Charts are lightweight HTML/CSS rather than an added chart dependency. Styles
use a shared token sheet and app stylesheet; v1 uses separate assets. React
type declarations and the plan-approved formatter are dev dependencies.
Credential state is kept only in tab memory; reloading requires sign-in.

## Verification scope

Backend/frontend tests and production builds run locally; GitHub Actions is
configured but has not run remotely. Browser checks cover sign-in, live
updates, card creation and disable confirmation, filters, devices, analytics
and system views at desktop/mobile breakpoints. Test reports contain actual
counts; no Lighthouse score or physical Pi measurements are estimated.

The original plan and Phase 1 review remain historical design context.
Arm/disarm, commands, video, accounts and push notifications remain out of scope.

## Verified delivery (2026-10-13)

- Python: 84 passed, 1 optional vision-module skip. Existing hub and node-agent
  tests remain green; new tests cover streams, slot release, live wiring,
  startup cleanup, camera cleanup and the RC522 protocol using fake hardware.
- Frontend: 12 tests passed, including shared API contracts, reconnect/polling,
  authorization expiry, CSV safety and card-disable rollback.
- Production build: JavaScript 95.71 KB gzip, CSS 5.86 KB gzip. The dependency
  audit after updating Vitest reported zero vulnerabilities.
- SQLite load: 1,200 writes at 20 events/second and 2,851 reads over 60 seconds,
  with no lock errors on this Windows development machine. This does not
  substitute for a check on Pi storage.
- Browser: sign-in, live connection, event filtering/search, three devices,
  device detail, 7-day charts, System readiness, and mobile create/disable flow
  passed. Desktop 1440px and mobile 390px had no horizontal overflow; the modal
  focused the UID input. No console errors were observed in the checked session.
- Pi preflight reports missing hardware dependencies/model/config accurately
  on the laptop. No physical Pi or Lighthouse score was tested.

The source bundle is generated from the committed branch with `git archive`;
`.gitattributes` excludes the tracked sample database. Models, credentials,
virtual environments, node_modules and runtime databases are absent. The
prebuilt dashboard is included. Extract the bundle on the Pi and follow
[RPI_START.md](RPI_START.md).
