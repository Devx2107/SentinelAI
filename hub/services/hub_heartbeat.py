"""Managed hub liveness using the existing heartbeat topic and payload."""
import logging
from threading import Event, Thread
from time import monotonic

from services.common import iso, utcnow
from shared.mqtt_topics import heartbeat_topic
from shared.schemas import HeartbeatPayload


class HubHeartbeat:
    def __init__(self, mqtt_client, refresh_device, node_id, interval=30, clock=utcnow):
        self.mqtt, self.refresh_device, self.node_id = mqtt_client, refresh_device, node_id
        self.interval, self.clock = interval, clock
        self.stop_event, self.thread = Event(), None
        self.started = monotonic()

    def tick(self):
        # Local liveness stays accurate even while the broker is reconnecting.
        self.refresh_device()
        payload = HeartbeatPayload(self.node_id, iso(self.clock()), max(0.0, monotonic() - self.started))
        self.mqtt.publish(heartbeat_topic(self.node_id), payload.to_json())

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        def run():
            while not self.stop_event.wait(self.interval):
                try:
                    self.tick()
                except Exception:
                    logging.getLogger(__name__).exception('Hub heartbeat failed')
        self.thread = Thread(target=run, name='sentinel-hub-heartbeat', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=6)
            if self.thread.is_alive():
                raise RuntimeError('Hub heartbeat did not stop within six seconds.')
