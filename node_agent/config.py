"""Configuration for SentinelAI node agents."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MQTTConfig:
    broker_host: str = os.getenv("SENTINELAI_MQTT_HOST", "localhost")
    broker_port: int = int(os.getenv("SENTINELAI_MQTT_PORT", "1883"))
    keepalive_seconds: int = 60
    client_id: str = os.getenv("SENTINELAI_MQTT_CLIENT_ID", "sentinelai-node")


@dataclass(frozen=True)
class NodeAgentConfig:
    node_id: str = os.getenv("SENTINELAI_NODE_ID", "node-1")
    heartbeat_interval_seconds: float = float(
        os.getenv("SENTINELAI_HEARTBEAT_INTERVAL", "10")
    )
    mqtt: MQTTConfig = field(default_factory=MQTTConfig)


config = NodeAgentConfig()
