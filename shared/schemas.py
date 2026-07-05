"""Shared MQTT message payload formats.

Both hub and node agents serialize/deserialize messages using these
dataclasses so the JSON shape never drifts between publisher and
subscriber.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass
class SensorStatePayload:
    """Payload published to a `<node_id>/<sensor_id>/state` topic."""

    sensor_id: str
    sensor_type: str
    state: str
    timestamp: str
    confidence: Optional[float] = None
    metadata: Optional[dict[str, Any]] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(payload: str) -> "SensorStatePayload":
        data = json.loads(payload)
        return SensorStatePayload(**data)


@dataclass
class HeartbeatPayload:
    """Payload published to a `<node_id>/heartbeat` topic."""

    node_id: str
    timestamp: str
    uptime_seconds: float

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(payload: str) -> "HeartbeatPayload":
        data = json.loads(payload)
        return HeartbeatPayload(**data)
