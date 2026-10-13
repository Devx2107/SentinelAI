# Dashboard 2.1: security insights, saved views and backups

No schema changes, hardware changes or added runtime dependencies are required.
The prebuilt UI is included; use the existing demo/live startup commands.

## Security insights

Overview now includes an authenticated `/api/v1/insights` panel. It shows warning
and critical counts over the last hour, denied card scans, the current 24-hour
event total compared with the preceding 24 hours, and the most active nodes.
Links open the matching event filters or device details.

Connection alerts identify stale/offline devices and a disconnected live MQTT
broker. These are deterministic summaries of recorded data, not an AI risk
score or an acknowledgement system. Each time window is half-open (inclusive
start, exclusive end). With no previous-day events, percentage change is null
and the UI shows "No previous baseline" instead of an invented percentage.

The response uses the shared API schema and runtime guard. It updates through
the existing stream/polling refresh path.

The live hub now publishes a managed heartbeat and refreshes its local device
record, preventing a running hub from becoming stale after startup. Its
interval adapts to the configured stale threshold and it stops with the
runtime. The existing topic and payload format are unchanged.

## Saved event views

Events has quick presets for recent warnings, denied access and the last 24
hours. "Save view" stores the current filter set under a name in this browser.
Select a saved view to reapply it or remove it with the adjacent button.

Up to ten views are stored in localStorage. Names are 1–40 characters and must
be unique ignoring case. Pagination, credentials and unknown query fields are
excluded. Date filters store the selected absolute dates; quick presets create
a fresh timestamp when clicked. Saved views do not sync between browsers.
Storage failures show an error without losing the current filters. Resetting
or manually changing filters clears a mismatched saved-view selection.

## Database snapshots

System now has "Download backup". The authenticated `GET /api/v1/backup` route
uses SQLite's backup API and checks the snapshot before returning it. The file
includes events, device records and trusted cards, including notes and UIDs.
Store it privately. Demo downloads contain only the current synthetic dataset.

Snapshots use temporary disk files and stream in 64 KiB chunks, rather than
loading the hub database into server memory. Temporary files and the download
slot are released after completion, failure or client disconnect. Only one
download runs at a time per app process; each IP may request three per minute.
Backup construction has a 15-second progress deadline for retryable busy cases.
Responses are not cached. Signing out aborts an in-progress browser request.

The download is a standard SQLite file. This release deliberately provides no
automatic restore action that could overwrite a running hub. To inspect a
copy independently, open it using a SQLite viewer or `sqlite3 backup.sqlite3`.
Restoring real data should be an offline, backed-up administration step.

## Verification

Backend tests cover hourly/day boundaries, empty baselines, connection alerts,
authorization, backup integrity, source writes after snapshot creation,
concurrent-download limits, timeout/failure cleanup and disconnect cleanup.
Frontend tests cover saved-view persistence, limits, duplicate names, preset
filters, reset behavior, unavailable storage and backup error recovery.
Shared fixtures include the new insights response.

Verified locally: 99 backend tests passed with 1 optional vision-module skip;
18 frontend tests passed; production build passed. JavaScript is 97.96 KB gzip
and CSS is 6.42 KB gzip. Browser checks confirmed live insights, saved-view
restoration/reset, backup download and layouts without horizontal overflow at
1440px and 390px. No console errors were observed in the checked session.
