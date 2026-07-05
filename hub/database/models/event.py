"""Event model — represents a single logged occurrence from any sensor.

This is the one shared record type all modules write to. Whether it's
a door module, motion module, or RFID module, they all produce Events.
Keeping `sensor` and `node_id` as plain strings (not foreign keys to a
rigid table-per-sensor-type schema) is deliberate: it lets new sensor
types plug in later without a database migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from database.db import db_cursor


@dataclass
class Event:
    node_id: str
    sensor: str
    status: str
    severity: str
    message: str
    confidence: Optional[float] = None
    timestamp: Optional[str] = None
    id: Optional[int] = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def create_event(event: Event) -> Event:
    """Insert an Event into the database and return it with its assigned id."""
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO events (timestamp, node_id, sensor, status, severity, confidence, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.timestamp,
                event.node_id,
                event.sensor,
                event.status,
                event.severity,
                event.confidence,
                event.message,
            ),
        )
        event.id = cur.lastrowid
    return event


def list_events(limit: int = 100, sensor: Optional[str] = None) -> list[Event]:
    """Return the most recent events, optionally filtered by sensor, newest first."""
    query = "SELECT * FROM events"
    params: tuple = ()
    if sensor is not None:
        query += " WHERE sensor = ?"
        params = (sensor,)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params = params + (limit,)

    with db_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        Event(
            id=row["id"],
            timestamp=row["timestamp"],
            node_id=row["node_id"],
            sensor=row["sensor"],
            status=row["status"],
            severity=row["severity"],
            confidence=row["confidence"],
            message=row["message"],
        )
        for row in rows
    ]


def get_latest_event(sensor: Optional[str] = None) -> Optional[Event]:
    """Return the single most recent event, optionally filtered by sensor."""
    events = list_events(limit=1, sensor=sensor)
    return events[0] if events else None
