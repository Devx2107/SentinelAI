# Telegram alerts

SentinelAI can message you on Telegram when the hub logs an event at or above a
severity you choose. The feature is optional and off by default. It only sends
messages: there are no bot commands, no arm/disarm, and no photos or video.

## What triggers an alert

Every module writes its events to the same `events` table, each with a severity
of `info`, `warning` or `critical`. The alerts module watches that table and
alerts on events at or above `SENTINELAI_TELEGRAM_MIN_SEVERITY` (default
`warning`).

With the modules that ship today, `warning` alerts cover:

| Event | Severity | Alerts at `warning`? |
| --- | --- | --- |
| Person confirmed at the entry with no active RFID authorization | `warning` | Yes |
| Unknown or disabled RFID card | `warning` | Yes |
| Authorized RFID card | `info` | No |
| Motion without a confirmed person | `info` | No |

No shipped module currently logs `critical`, so setting the threshold to
`critical` sends nothing until a module does. Severity names the hub does not
recognise are treated as `warning`.

Only events logged after the hub starts can alert. History is never replayed on
restart.

## Setup

1. In Telegram, open a chat with `@BotFather`, send `/newbot` and follow the
   prompts. Copy the token it gives you. Treat it like a password.
2. Choose where alerts go:
   - **Your own chat:** open your new bot and send it any message.
   - **A group:** add the bot to the group and send a message there.
   - **A channel:** add the bot as an administrator and use the channel's
     `@name` as the chat ID.
3. Find the chat ID for a private chat or group. Send a message to the bot, then
   open this address in a browser, replacing `<TOKEN>` with your token:

   ```text
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

   Look for `"chat":{"id": ...}`. Private chat IDs are positive numbers and
   group IDs are negative. Don't share or paste this page anywhere, since the
   address contains your token.
4. Add the settings to the `.env` file at the repository root (see
   `deploy/sentinelai.env.example`):

   ```text
   SENTINELAI_TELEGRAM_BOT_TOKEN=123456789:AA...
   SENTINELAI_TELEGRAM_CHAT_ID=123456789
   ```

5. Install the library on the Pi if it is not already there (it is included in
   `deploy/requirements-live.txt`):

   ```sh
   python -m pip install -r deploy/requirements-live.txt
   ```

6. Check the configuration, then start the hub:

   ```sh
   python hub/run.py --mode live --check
   python hub/run.py --mode live
   ```

   The log should show `Telegram alerts ready (bot @your_bot_name)` and
   `Telegram alerts started (minimum severity: warning)`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `SENTINELAI_TELEGRAM_BOT_TOKEN` | Unset | Bot token from BotFather |
| `SENTINELAI_TELEGRAM_CHAT_ID` | Unset | Destination chat ID or `@channel` name |
| `SENTINELAI_TELEGRAM_MIN_SEVERITY` | `warning` | `info`, `warning` or `critical` |
| `SENTINELAI_TELEGRAM_COOLDOWN_SECONDS` | `60` | Minimum seconds between alerts for the same node, sensor and status (0 disables) |
| `SENTINELAI_TELEGRAM_MAX_PER_MINUTE` | `20` | Global ceiling on alerts per minute, 1 to 120 |
| `SENTINELAI_TELEGRAM_POLL_SECONDS` | `2` | How often the hub checks for new events, 0.5 to 60 |

Alerts are enabled only when both the token and chat ID are set. If neither is
set the module is not even loaded. Setting only one is reported by
`--check`.

## What a message looks like

```text
⚠️ WARNING · card_denied
RFID card ****B2C3 rejected
Node: hub · Sensor: rfid_auth
Time: 2026-11-11 10:30:00 UTC
```

Person detections also show a confidence percentage. Times are in UTC.

## Behavior

- **Cooldown.** After an alert, further events with the same node, sensor and
  status are held back for the cooldown period. The next alert that gets
  through says how many were suppressed, for example
  `(+3 similar event(s) suppressed since the last alert)`.
- **Rate cap.** No more than the configured number of alerts go out per minute
  across all event types. Events over the cap are counted the same way.
- **Delivery.** Messages are sent from a background thread. Network problems are
  retried with increasing delays, and Telegram's own rate-limit replies are
  honored. Delivery problems never delay or stop event logging or the hub.
- **Queue.** Up to 50 alerts wait for delivery. If Telegram stays unreachable
  and the queue fills, the oldest alerts are dropped (the log says so).
- **Shutdown.** Alerts still waiting when the hub stops are not delivered.
- **Rejected token.** If Telegram rejects the token, alerts are disabled until
  the hub restarts and the log says so. The hub keeps running.

## Privacy and security

- Messages pass through Telegram's servers and are not end-to-end encrypted.
  Anyone in the destination chat or channel can read them.
- RFID card UIDs are masked to their last four characters before sending. Card
  labels, node names and event text are sent as logged.
- The bot token is never written to logs or the configuration display. Anyone
  holding it can send messages as your bot, so keep `.env` private and revoke
  the token in BotFather (`/revoke`) if it leaks.

## Test it

With the hub running, add a harmless test event to the live database from the
repository root. It also appears in the dashboard's event log.

```sh
python - <<'PY'
import os, sqlite3
db = os.getenv("SENTINELAI_DB_PATH", "data/sentinelai.db")
with sqlite3.connect(db) as conn:
    conn.execute(
        "INSERT INTO events (timestamp, node_id, sensor, status, severity, message) "
        "VALUES (datetime('now'), 'hub', 'manual_test', 'telegram_test', 'warning', 'Telegram alert test')"
    )
PY
```

A message should arrive within a few seconds. If you set a custom
`SENTINELAI_DB_PATH`, export it first or run the snippet with the same value.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `--check` reports `telegram_credentials` | Only one of the token and chat ID is set |
| `--check` reports `telegram_bot_token` | The token has quotes, spaces or a typo; it looks like `123456789:AA...` |
| `--check` reports `python_telegram_bot` | The library is missing; install `deploy/requirements-live.txt` |
| Log says `Telegram bot token was rejected` | The token is wrong or revoked |
| Log says `Telegram rejected an alert` with `chat not found` | Wrong chat ID, or you have not messaged the bot yet |
| Log says `Telegram rejected an alert` with `Forbidden` | The bot was blocked or removed from the chat |
| Log says `Could not verify the Telegram bot yet` | No network at startup. Alerts are still attempted and will work once the connection returns |
| Nothing arrives and nothing is logged | The threshold is above the event's severity, or the event is in a cooldown or over the rate cap |

If the hub runs under systemd as in `deploy/sentinelai.service`, read the log
with `journalctl -u sentinelai -f`.

Alerts are not sent in demo mode.
