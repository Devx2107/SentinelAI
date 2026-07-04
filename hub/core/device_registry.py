"""In-memory device registry.

Tracks which nodes are currently online and what capabilities they've
announced, by listening to MQTT status/heartbeat topics. This is the
hub's live view of the network — the `database.models.device` module
is the durable backing store, updated from here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from database.models.device import Device, upsert_device
from shared.mqtt_topics import ALL_STATUS_WILDCARD, ALL_HEARTBEAT_WILDCARD

logger = logging.getLogger(__name__)


@dataclass
class DeviceRecord:
    node_id: str
    status: str = "offline"
    last_seen: Optional[str] = None
    capabilities: list[str] = field(default_factory=list)


class DeviceRegistry:
    """Tracks live device status, backed by MQTT status/heartbeat messages."""

    def __init__(self) -> None:
        self._devices: dict[str, DeviceRecord] = {}

    def register_with_mqtt(self, mqtt_client) -> None:
        """Subscribe to status and heartbeat topics for all nodes."""
        mqtt_client.subscribe(ALL_STATUS_WILDCARD, self._on_status_message)
        mqtt_client.subscribe(ALL_HEARTBEAT_WILDCARD, self._on_heartbeat_message)

    def _on_status_message(self, topic: str, payload: str) -> None:
        node_id = self._node_id_from_topic(topic)
        record = self._devices.setdefault(node_id, DeviceRecord(node_id=node_id))
        record.status = payload
        record.last_seen = datetime.now(timezone.utc).isoformat()
        logger.info("Node '%s' status -> %s", node_id, payload)
        self._persist(record)

    def _on_heartbeat_message(self, topic: str, payload: str) -> None:
        node_id = self._node_id_from_topic(topic)
        record = self._devices.setdefault(node_id, DeviceRecord(node_id=node_id))
        record.status = "online"
        record.last_seen = datetime.now(timezone.utc).isoformat()
        self._persist(record)

    @staticmethod
    def _node_id_from_topic(topic: str) -> str:
        # Topics look like "sentinelai/<node_id>/status" or ".../heartbeat"
        return topic.split("/")[1]

    @staticmethod
    def _persist(record: DeviceRecord) -> None:
        upsert_device(
            Device(
                node_id=record.node_id,
                status=record.status,
                last_seen=record.last_seen,
                capabilities=record.capabilities,
            )
        )

    def get_all(self) -> list[DeviceRecord]:
        """Return the current in-memory state of all known devices."""
        return list(self._devices.values())

    def get(self, node_id: str) -> Optional[DeviceRecord]:
        return self._devices.get(node_id)

    def register_local_device(self, node_id: str, capabilities: list[str]) -> None:
        """Manually register a device the hub knows about at startup

        (used for the hub itself, which doesn't need to hear its own
        MQTT status message to know it's online).
        """
        record = DeviceRecord(
            node_id=node_id,
            status="online",
            last_seen=datetime.now(timezone.utc).isoformat(),
            capabilities=capabilities,
        )
        self._devices[node_id] = record
        self._persist(record)
