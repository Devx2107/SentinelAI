"""Tests for the node agent runtime."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from node_agent.agent import NodeAgent
from shared.base_sensor import BaseSensor


@dataclass
class PublishedMessage:
    topic: str
    payload: str
    retain: bool


class FakeMQTTClient:
    def __init__(self) -> None:
        self.published: list[PublishedMessage] = []
        self.connected = False
        self.disconnected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        self.published.append(PublishedMessage(topic, payload, retain))

    def subscribe(self, topic: str, callback) -> None:
        return None


class FakeSensor(BaseSensor):
    sensor_type = "fake"

    def __init__(self, sensor_id: str) -> None:
        self.sensor_id = sensor_id
        self._callbacks = []
        self.closed = False

    def read(self) -> str:
        return "idle"

    def on_change(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self, state: str) -> None:
        for callback in self._callbacks:
            callback(state)

    def close(self) -> None:
        self.closed = True


def test_node_agent_publishes_online_heartbeat_and_sensor_state():
    mqtt_client = FakeMQTTClient()
    sensor = FakeSensor("entry")
    agent = NodeAgent(
        node_id="node-1",
        mqtt_client=mqtt_client,
        sensors=[sensor],
        heartbeat_interval_seconds=60,
    )

    agent.start()
    sensor.emit("motion")
    agent.stop()

    topics = [message.topic for message in mqtt_client.published]
    assert "sentinelai/node-1/status" in topics
    assert "sentinelai/node-1/heartbeat" in topics
    assert "sentinelai/node-1/entry/state" in topics
    assert mqtt_client.connected is True
    assert mqtt_client.disconnected is True
    assert sensor.closed is True
