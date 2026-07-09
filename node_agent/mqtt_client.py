"""MQTT client wrapper for node agents."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from node_agent.config import config
from shared.mqtt_topics import status_topic

logger = logging.getLogger(__name__)

MessageCallback = Callable[[str, str], None]

try:  # pragma: no cover - optional dependency in non-Pi environments
    import paho.mqtt.client as mqtt
except ModuleNotFoundError:  # pragma: no cover - exercised when paho is absent
    mqtt = None


class MQTTClient:
    """Thin wrapper around paho-mqtt for node-side pub/sub."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, MessageCallback] = {}
        self._enabled = mqtt is not None

        if not self._enabled:
            logger.warning(
                "paho-mqtt is not installed; node agent MQTT is disabled and will run offline."
            )
            self._client = None
            return

        self._client = mqtt.Client(client_id=config.mqtt.client_id)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.will_set(status_topic(config.node_id), payload="offline", retain=True)

    def connect(self) -> None:
        if not self._enabled:
            return

        self._client.connect(
            config.mqtt.broker_host,
            config.mqtt.broker_port,
            config.mqtt.keepalive_seconds,
        )
        self._client.loop_start()

    def disconnect(self) -> None:
        if not self._enabled:
            return

        self.publish(status_topic(config.node_id), "offline", retain=True)
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        if not self._enabled:
            logger.debug("MQTT disabled; dropping publish to %s", topic)
            return

        result = self._client.publish(topic, payload, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("Failed to publish to %s (rc=%s)", topic, result.rc)

    def subscribe(self, topic: str, callback: MessageCallback) -> None:
        if not self._enabled:
            return

        self._subscriptions[topic] = callback
        self._client.subscribe(topic)
        self._client.message_callback_add(topic, self._wrap_callback(callback))

    @staticmethod
    def _wrap_callback(callback: MessageCallback):
        def _handler(_client, _userdata, msg) -> None:
            try:
                callback(msg.topic, msg.payload.decode("utf-8"))
            except Exception:
                logger.exception("Error handling message on topic %s", msg.topic)

        return _handler

    def _on_connect(self, _client, _userdata, _flags, rc: int) -> None:
        if rc == 0:
            logger.info(
                "Connected to MQTT broker at %s:%s",
                config.mqtt.broker_host,
                config.mqtt.broker_port,
            )
            self.publish(status_topic(config.node_id), "online", retain=True)
        else:
            logger.error("Failed to connect to MQTT broker (rc=%s)", rc)

    def _on_disconnect(self, _client, _userdata, rc: int) -> None:
        if rc != 0:
            logger.warning("Unexpected MQTT disconnect (rc=%s)", rc)


_client_instance: Optional[MQTTClient] = None


def get_mqtt_client() -> MQTTClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = MQTTClient()
    return _client_instance

