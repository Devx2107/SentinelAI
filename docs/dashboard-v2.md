# Dashboard v2: Phase 1 backend

> Historical Phase 1 notes. The completed UI, streams and live startup are
> documented in [dashboard-v2-complete.md](dashboard-v2-complete.md) and
> [RPI_START.md](RPI_START.md).

This phase adds an authenticated REST API and an isolated, seeded demo runner.
The existing dashboard at `/dashboard` is preserved. The React application at
`/app/` and live SSE feed are later phases, not part of this delivery.

## Run locally without hardware

Use Python 3.11 (the existing NumPy pin supports it). From this checkout:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install flask==3.0.3 pytest==8.2.2 numpy==1.26.4
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python hub/dashboard_dev.py
```

On Linux/macOS use `python3.11 -m venv .venv` and `.venv/bin/python` in place
of the Windows commands. Only existing dependency names/versions are used.
NumPy is required by the unchanged legacy test module, not by the dashboard.
No paho, camera, GPIO, LiteRT, broker or hardware is required.

In another terminal:

```powershell
curl.exe -u admin:dev http://127.0.0.1:5001/api/v1/overview
curl.exe -u admin:dev "http://127.0.0.1:5001/api/v1/events?limit=10&severity=warning,critical"
```

The runner binds only to loopback. `admin` / `dev` defaults exist only in the
dev runner. Override with `SENTINELAI_DASHBOARD_USER` and
`SENTINELAI_DASHBOARD_PASSWORD`; empty credentials produce a clear 500 error.
The default database is new, temporary and seeded with 800 events, 3 devices
and 4 synthetic cards. It is cleaned up when the runner exits normally.
Device ages continue advancing; without Phase 2's generator, demo online
devices become stale after 90 seconds. This is expected, not a live heartbeat.

`SENTINELAI_DB_PATH` may point to a **new** file; existing files are refused,
including the committed hub DB. The runner never deletes a user-specified
file. To preserve a deterministic sample explicitly:

```powershell
.\.venv\Scripts\python hub/tools/seed_demo_data.py ./sample-demo.db --as-of 2026-10-13T12:00:00Z
```

The seed command also refuses to overwrite. An injected reference time and
RNG seed reproduce data. `SENTINELAI_STALE_AFTER_SECONDS` defaults to 90 and
accepts positive integers up to 86400. `SENTINELAI_NODE_ID` defaults to `hub`.

## Architecture and contract

`hub/api/v1.py` handles Flask transport and auth. Pure Python services receive
`app.extensions['sentinel_providers']`: per-app Store, clock, authorization
window, connection status and database event source. Connections close after
each query/transaction. Live adapters accept injected objects/callables and
remain unwired; nothing imports hardware from the demo graph.

The new blueprint is registered in `hub/app.py` with exactly one import and
one registration. Until Phase 8 supplies live providers, its v2 routes return
503 (after authentication). Dashboard v1 remains functional and unchanged.

The machine-readable response contract is
[`responses.json`](../dashboard-ui/src/api/schema/responses.json), with a
strict subset validator in the backend tests. The reviewed refinements to the
external plan are in [dashboard-v2-review.md](dashboard-v2-review.md).

All protected endpoints use HTTP Basic auth. Errors use
`{"error":{"code":"...","message":"..."}}`. Requests are not cached.
Writes require same-origin JSON, are limited to 16 KiB, and validate field
types. UID normalization strips outer whitespace and uppercases hex; the
regex is `^[0-9A-F]{8,20}$`. No separators are removed. Labels are trimmed,
1–40 characters; notes are null or at most 2000 characters. Active must be
a JSON boolean. Unsupported fields are rejected.

| Route | Response / behavior |
| --- | --- |
| GET `/api/v1/health` | Public status, node ID, uptime, DB availability, version; 503 when unavailable |
| GET `/api/v1/overview` | Hub, 24h counts, effective device counts, auth window, latest 10 events |
| GET `/api/v1/devices` | Devices with effective status and age |
| GET `/api/v1/devices/<node_id>` | Device plus latest 20 node events; 404 if absent |
| GET `/api/v1/events` | Events, next_cursor, total_matching |
| GET `/api/v1/events/summary` | Zero-filled severity series and sensor totals |
| GET `/api/v1/rfid/cards` | Known cards |
| POST `/api/v1/rfid/cards` | Create UID/label/optional notes; 201 or atomic duplicate 409 |
| PATCH `/api/v1/rfid/cards/<uid>` | Update only label, notes, active; no deletion |
| GET `/api/v1/rfid/activity` | RFID events; limit 1–200, default 50 |
| GET `/api/v1/entry-monitor/stats` | Counts, mean confirmed confidence, histogram, time series |
| GET `/api/v1/system` | Counts, DB basename/size, uptime, mode, MQTT availability |

Events accept `limit` (1–200, default 50), `cursor` (positive ID), `sensor`,
`node_id`, comma lists `severity`/`status`, timezone-aware `since`/`until`,
and `q` (literal case-insensitive ASCII substring, max 500 characters).
Date ranges are half-open: since inclusive, until exclusive. Offset and Z
timestamps compare as instants. Results order by ID descending; counts ignore
the cursor. `next_cursor` is null only when there are no more matching rows.
Counts and page use the same SQLite read snapshot.

Summary accepts `range=24h|7d` and `bucket=hour|day`; entry stats accepts
`range=24h|7d`. Buckets use UTC; timestamps on Event records are unchanged.
Rolling windows include partial first/last calendar buckets. Histogram bins
span 0–1 for confirmed events, include 1.0 in the final bin, and exclude null
confidence. Empty averages are null. No status inference writes to the DB.

## Verification and future work

Run `python -m pytest -q` for both suites. New tests exercise auth, contract
shapes, filter injection, timezone bounds, pagination, stale status, concurrent
card creation, histogram edges, seeding safety, app isolation and import safety.
Real HTTP smoke checks supplement the Flask test-client suite.

Phases 2–7 add SSE, the SPA, management UI, analytics charts and final hardening.
Frontend TypeScript runtime checks must reuse this schema and seed reference
time. No accessibility score or frontend bundle size is claimed in Phase 1.

Pi integration readiness checklist (Phase 8 only):

- Obtain explicit authorization to wire the actual auth-state/MQTT providers.
- Keep demo generator disabled and confirm the existing DB schema.
- Validate reader/writer load and SQLite contention before proposing WAL.
- Measure a 30-minute SSE session, memory/CPU and stream caps on hardware.
- Verify real PIR/RFID events and producer-driven offline states from a phone.
- Keep v1 available until its retirement is separately approved.

Arm/disarm, commands, snapshots, accounts, acknowledgements, remote access and
unsupported sensor pages remain out of scope.
