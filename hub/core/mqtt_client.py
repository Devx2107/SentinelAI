"""MQTT client wrapper for the hub.

Wraps paho-mqtt with SentinelAI-specific defaults: automatic Last Will
and Testament (LWT) registration so that if the hub itself disconnects
uncleanly, the broker publishes an "offline" status on its behalf, and
a simple callback-registration API so modules don't need to know
anything about paho-mqtt directly.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from config import config
from shared.mqtt_topics import status_topic

logger = logging.getLogger(__name__)

MessageCallback = Callable[[str, str], None]  # (topic, payload) -> None

try:
    import paho.mqtt.client as mqtt
except ModuleNotFoundError:  # pragma: no cover - exercised in non-Pi dev setups
    mqtt = None


class MQTTClient:
    """Thin wrapper around paho-mqtt for hub-side pub/sub."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, MessageCallback] = {}
        self._enabled = mqtt is not None

        if not self._enabled:
            logger.warning(
                "paho-mqtt is not installed; MQTT is disabled and the hub will run in dashboard-only mode."
            )
            self._client = None
            return

        self._client = mqtt.Client(client_id=config.mqtt.client_id)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        # LWT: if this client disconnects uncleanly, the broker will
        # publish "offline" on our behalf, retained so late subscribers
        # (e.g. a dashboard that just loaded) see the correct last state.
        self._client.will_set(
            status_topic(config.node.node_id), payload="offline", retain=True
        )

    def connect(self) -> None:
        """Connect to the configured broker and start the network loop thread."""
        if not self._enabled:
            logger.info("MQTT disabled; skipping broker connection.")
            return

        self._client.connect(
            config.mqtt.broker_host,
            config.mqtt.broker_port,
            config.mqtt.keepalive_seconds,
        )
        self._client.loop_start()

    def disconnect(self) -> None:
        """Publish a clean 'offline' status and disconnect."""
        if not self._enabled:
            return

        self.publish(status_topic(config.node.node_id), "offline", retain=True)
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        """Publish a message to a topic."""
        if not self._enabled:
            logger.debug("MQTT disabled; dropping publish to %s", topic)
            return

        result = self._client.publish(topic, payload, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("Failed to publish to %s (rc=%s)", topic, result.rc)

    def subscribe(self, topic: str, callback: MessageCallback) -> None:
        """Subscribe to a topic (supports MQTT wildcards) with a callback.

        The callback receives (topic, payload) for every matching message.
        """
        if not self._enabled:
            logger.debug("MQTT disabled; skipping subscribe to %s", topic)
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
            logger.info("Connected to MQTT broker at %s:%s", config.mqtt.broker_host, config.mqtt.broker_port)
            # Announce ourselves as online, retained so late subscribers see it.
            self.publish(status_topic(config.node.node_id), "online", retain=True)
        else:
            logger.error("Failed to connect to MQTT broker (rc=%s)", rc)

    def _on_disconnect(self, _client, _userdata, rc: int) -> None:
        if rc != 0:
            logger.warning("Unexpected MQTT disconnect (rc=%s)", rc)


_client_instance: Optional[MQTTClient] = None


def get_mqtt_client() -> MQTTClient:
    """Return the process-wide MQTTClient singleton, creating it if needed."""
    global _client_instance
    if _client_instance is None:
        _client_instance = MQTTClient()
    return _client_instance
