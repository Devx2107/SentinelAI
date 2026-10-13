# Dashboard v2 plan review and refinements

Reviewed 2026-10-13 against the provided `DASHBOARD_V2_PLAN.md` and fetched refs.

## Phase 0 audit

- `origin/main`: `893427b31dffedfdf119a3f5a133d59df48d1db3`; lacks dashboard v1, RFID and node_agent.
- Required features exist on `origin/feature/phase4-rfid-auth` at `b5b44854aec8b30b08ee3c8dbc43176807549a88`.
- The user authorized an isolated checkout of that branch. Current working changes on main are preserved. The dashboard branch starts at this exact RFID commit, not origin/main.
- `hub/database/sentinelai.db` is tracked on the RFID branch. Do not open it for demo/tests or include it in the patch.
- The original checkout's prior reliability work modifies protected files. It is not carried into this checkout or this patch.
- A bare core-only environment cannot collect the unchanged vision tests: they import NumPy before skipping the optional runtime. Install the existing `numpy==1.26.4` dependency on Python 3.11; no test edits are needed.
- With the existing dependency pins installed, the baseline hub suite passed 11 tests with 1 optional-vision skip; the node-agent suite passed 1 test.

## Revised implementation decisions

1. Preserve the original phase boundaries and protected-file list. This delivery implements Phase 1 only. Pi integration remains separately authorized Phase 8.
2. Use a recorded base commit for each patch. Later phases build on the preceding accepted phase; repeatedly branching from an unchanged main would lose their prerequisites. Do not generate this patch against origin/main because that would accidentally include the entire RFID branch.
3. Services use an explicit app-scoped `Store` rather than mutating imported global database configuration. The schema is unchanged and comes from the existing schema definition when creating demo databases. Existing paths are opened in read/write-existing mode so typos do not silently create empty live databases.
4. Demo seeding exclusively creates a NEW file and rejects existing paths, especially the committed DB. Default runner data lives in a temporary directory with cleanup on exit. RNG plus an injected reference time makes fixtures reproducible. Synthetic critical events are clearly tagged DEMO.
5. POST RFID uses an atomic INSERT and translates duplicate-UID constraints to 409. PATCH only updates submitted allowlisted fields in one transaction, preserving creation/last-seen fields. This intentionally replaces the plan's proposed use of `get_known_card` + `upsert_known_card`: that combination races and can overwrite concurrent changes. Existing model files remain untouched.
6. Define event ranges as `since <= timestamp < until`, require explicit timezone offsets, and convert timestamps for comparisons rather than comparing raw strings. IDs order pagination. `total_matching` counts all filtered matches independently of cursor, and `next_cursor` exists only when another row exists. Text search treats `%` and `_` literally (SQLite's built-in case folding is ASCII).
7. Rolling summaries include partial first/last UTC calendar buckets; a 24-hour range can span 25 hourly buckets. Zero-fill all intersecting buckets. Entry histograms include confirmed-person confidences across ten bins from 0 to 1; bins are left-inclusive/right-exclusive except the final bin includes 1.0. This avoids dropping valid low-confidence detections if the configured threshold changes. Empty average confidence is null.
8. Unknown/malformed last-seen values on online devices are stale; negative clock skew clamps age to zero. This is a read-time view and never updates device rows. Stale alone does not become offline without a producer publishing that state.
9. Move constant-time auth, same-origin JSON-only writes, body limits, no-store and basic response headers into Phase 1. Future rate limiting/CSP remain Phase 7. No credentials, full DB paths or internal errors appear in responses. Health is unauthenticated, returns 503/degraded when the DB cannot be read; protected hub routes return 503 until providers are wired, not fake demo state.
10. Phase 3 must establish same-origin browser Basic auth before opening native EventSource: it cannot attach arbitrary Authorization headers. Protect the SPA navigation with the same realm or use a fetch-based stream; never put credentials in URLs or localStorage. The Vite proxy must share that origin.
11. Phase 2 must capture the initial max event ID before yielding the first SSE chunk; reconnects use validated Last-Event-ID. Only event rows carry an SSE id. Reserve/release the stream cap under a lock, including early client disconnects. The demo generator belongs to app lifetime, not each connection; do not stop a shared generator when one subscriber disconnects.
12. Use a JSON-schema subset with a standard-library test validator in Phase 1 (no added Python dependency). Phase 3 adds TypeScript runtime-guard parity and the frontend runner. The plan's hourly-warning banner needs an explicit hourly count contract before it can be implemented; 24-hour warnings cannot stand in for it.
13. The frontend whitelist omits React TypeScript declarations. Resolve whether to add `@types/react` / `@types/react-dom` before Phase 3 rather than silently substituting untyped declarations. Lighthouse and live-Pi measurements must be recorded from actual runs, never estimated.

## Delivery boundaries

Phase 1 ships REST, providers, seed tool, runner, backend contract fixtures/tests and docs.
It does not ship the SPA, SSE, generator thread, live provider wiring, deployment or hardware changes.
The original external plan is preserved; this document records its reviewed refinements.

## Phase 1 verification

- Combined suites: 63 passed, 1 skipped on Python 3.11. The skipped module requires the optional vision runtime. The original tests are unchanged.
- A real subprocess running `python hub/dashboard_dev.py` served health and authenticated overview, events, summary, device, entry stats and system responses over loopback HTTP. Card create returned 201 and disable returned 200.
- A fresh-interpreter test proves the demo imports no modules.*, MQTT client, module loader, paho, gpiozero, picamera2 or ai_edge_litert.
- Protected-file diff: only `hub/app.py` changed, by the allowed one import and one blueprint registration. The tracked database has no Git changes.
- Schema contract checks cover every Phase 1 endpoint. TypeScript/browser tests, SSE, Lighthouse and hardware checks belong to later phases and were not run.
