"""Alert policy: severity filter, cooldown, global rate cap and message text.

Pure logic with no I/O and an injectable clock, so it is easy to test and
cannot block or fail the hub.
"""

from __future__ import annotations

import re
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Optional

from database.models.event import Event

SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
VALID_SEVERITIES = tuple(SEVERITY_RANK)
# Severity is free text in the database. An unrecognised value is treated like
# "warning" so a future module's alert is never silently ignored.
UNKNOWN_SEVERITY_RANK = SEVERITY_RANK["warning"]

MAX_MESSAGE_CHARS = 500
RATE_WINDOW_SECONDS = 60.0

_ICONS = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}
_CARD_UID = re.compile(r"(?<=RFID card )\S+")


def severity_rank(severity: object) -> int:
    return SEVERITY_RANK.get(str(severity).strip().lower(), UNKNOWN_SEVERITY_RANK)


def mask_card_uid(text: str) -> str:
    """Hide all but the last four characters of an RFID card UID in a message."""

    def mask(match: re.Match) -> str:
        uid = match.group(0)
        return "****" + uid[-4:] if len(uid) > 4 else "****"

    return _CARD_UID.sub(mask, text)


def _format_time(timestamp: Optional[str]) -> str:
    if not timestamp:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return timestamp
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def format_alert(event: Event, suppressed: int = 0) -> str:
    """Build the plain-text Telegram message for an event."""
    severity = str(event.severity).strip().lower()
    message = mask_card_uid(str(event.message))
    if len(message) > MAX_MESSAGE_CHARS:
        message = message[: MAX_MESSAGE_CHARS - 1] + "…"

    lines = [
        f"{_ICONS.get(severity, '⚠️')} {severity.upper()} · {event.status}",
        message,
        f"Node: {event.node_id} · Sensor: {event.sensor}",
    ]
    if event.confidence is not None:
        try:
            lines.append(f"Confidence: {float(event.confidence):.0%}")
        except (TypeError, ValueError):
            pass
    lines.append(f"Time: {_format_time(event.timestamp)}")
    if suppressed:
        lines.append(f"(+{suppressed} similar event(s) suppressed since the last alert)")
    return "\n".join(lines)


class AlertPolicy:
    """Decides which events become alerts and what the message says."""

    def __init__(
        self,
        min_severity: str = "warning",
        cooldown_seconds: float = 60.0,
        max_per_minute: int = 20,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        normalized = str(min_severity).strip().lower()
        if normalized not in SEVERITY_RANK:
            raise ValueError(
                f"min_severity must be one of {', '.join(VALID_SEVERITIES)}; got {min_severity!r}"
            )
        self._min_rank = SEVERITY_RANK[normalized]
        self._cooldown = max(0.0, float(cooldown_seconds))
        self._max_per_minute = max(1, int(max_per_minute))
        self._clock = clock
        self._last_sent: dict[tuple[str, str, str], float] = {}
        self._suppressed: dict[tuple[str, str, str], int] = {}
        self._recent: deque[float] = deque()

    def evaluate(self, event: Event) -> Optional[str]:
        """Return the alert text for an event, or None if it should not be sent."""
        if severity_rank(event.severity) < self._min_rank:
            return None

        key = (event.node_id, event.sensor, event.status)
        now = self._clock()

        last = self._last_sent.get(key)
        if last is not None and now - last < self._cooldown:
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            return None

        while self._recent and now - self._recent[0] >= RATE_WINDOW_SECONDS:
            self._recent.popleft()
        if len(self._recent) >= self._max_per_minute:
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            return None

        self._last_sent[key] = now
        self._recent.append(now)
        return format_alert(event, self._suppressed.pop(key, 0))
