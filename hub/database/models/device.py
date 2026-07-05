"""Device model — persists the state of every known node on the network.

The in-memory DeviceRegistry (core/device_registry.py) is the fast path
used during normal operation. This module is the durable backing store
so device status survives a hub restart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from database.db import db_cursor


@dataclass
class Device:
    node_id: str
    status: str = "offline"
    last_seen: Optional[str] = None
    capabilities: Optional[list[str]] = None


def upsert_device(device: Device) -> None:
    """Insert or update a device's record."""
    capabilities_json = json.dumps(device.capabilities or [])
    last_seen = device.last_seen or datetime.now(timezone.utc).isoformat()

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO devices (node_id, status, last_seen, capabilities)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                status = excluded.status,
                last_seen = excluded.last_seen,
                capabilities = excluded.capabilities
            """,
            (device.node_id, device.status, last_seen, capabilities_json),
        )


def list_devices() -> list[Device]:
    """Return all known devices."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM devices")
        rows = cur.fetchall()

    return [
        Device(
            node_id=row["node_id"],
            status=row["status"],
            last_seen=row["last_seen"],
            capabilities=json.loads(row["capabilities"]) if row["capabilities"] else [],
        )
        for row in rows
    ]


def get_device(node_id: str) -> Optional[Device]:
    """Return a single device by node_id, or None if unknown."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM devices WHERE node_id = ?", (node_id,))
        row = cur.fetchone()

    if row is None:
        return None

    return Device(
        node_id=row["node_id"],
        status=row["status"],
        last_seen=row["last_seen"],
        capabilities=json.loads(row["capabilities"]) if row["capabilities"] else [],
    )
