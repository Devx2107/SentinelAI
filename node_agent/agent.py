"""Node agent runtime for SentinelAI distributed nodes."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Iterable, Optional

from node_agent.config import config
from node_agent.mqtt_client import MQTTClient, get_mqtt_client
from shared.base_sensor import BaseSensor
from shared.mqtt_topics import heartbeat_topic, sensor_state_topic, status_topic
from shared.schemas import HeartbeatPayload, SensorStatePayload

logger = logging.getLogger(__name__)


class NodeAgent:
    """Owns the MQTT connection, heartbeat loop, and sensor publishing."""

    def __init__(
        self,
        node_id: str,
        mqtt_client: Optional[MQTTClient] = None,
        sensors: Optional[Iterable[BaseSensor]] = None,
        heartbeat_interval_seconds: Optional[float] = None,
    ) -> None:
        self.node_id = node_id
        self._mqtt_client = mqtt_client or get_mqtt_client()
        self._sensors = list(sensors or [])
        self._heartbeat_interval_seconds = (
            heartbeat_interval_seconds or config.heartbeat_interval_seconds
        )
        self._started_at = datetime.now(timezone.utc)
        self._stop_event = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        logger.info("Starting node agent for node_id=%s", self.node_id)
        self._mqtt_client.connect()
        self._mqtt_client.publish(status_topic(self.node_id), "online", retain=True)
        self.send_heartbeat()

        for sensor in self._sensors:
            sensor.on_change(self._publish_sensor_state(sensor))

        self._stop_event.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def stop(self) -> None:
        logger.info("Stopping node agent for node_id=%s", self.node_id)
        self._stop_event.set()
        for sensor in self._sensors:
            try:
                sensor.close()
            except Exception:
                logger.exception("Error closing sensor '%s'", sensor.sensor_id)
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)
        self._mqtt_client.disconnect()

    def send_heartbeat(self) -> None:
        uptime_seconds = (datetime.now(timezone.utc) - self._started_at).total_seconds()
        payload = HeartbeatPayload(
            node_id=self.node_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            uptime_seconds=uptime_seconds,
        )
        self._mqtt_client.publish(
            heartbeat_topic(self.node_id),
            payload.to_json(),
            retain=False,
        )

    def _publish_sensor_state(self, sensor: BaseSensor):
        def _handler(state: str) -> None:
            payload = SensorStatePayload(
                sensor_id=sensor.sensor_id,
                sensor_type=sensor.sensor_type,
                state=state,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._mqtt_client.publish(
                sensor_state_topic(self.node_id, sensor.sensor_id),
                payload.to_json(),
                retain=True,
            )

        return _handler

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(self._heartbeat_interval_seconds):
            self.send_heartbeat()


def build_default_agent() -> NodeAgent:
    """Build a minimal node agent for a single node_id."""
    return NodeAgent(node_id=config.node_id)

