"""RFID authentication module."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from config import config
from core.auth_state import RfidAuthState
from database.models.event import Event, create_event
from database.models.rfid import get_known_card, touch_known_card
from modules.base_module import BaseModule
from modules.rfid_auth.reader import BaseCardReader
from shared.mqtt_topics import sensor_state_topic
from shared.schemas import SensorStatePayload

logger = logging.getLogger(__name__)

MODULE_ID = "rfid_auth"
SENSOR_ID = "rc522_entry"

STATUS_AUTHORIZED = "card_authorized"
STATUS_DENIED = "card_denied"


class RfidAuthModule(BaseModule):
    """Tap-to-authenticate RFID module backed by a known-card registry."""

    module_id = MODULE_ID

    def __init__(
        self,
        mqtt_client,
        auth_state: Optional[RfidAuthState] = None,
        reader: Optional[BaseCardReader] = None,
    ) -> None:
        self._mqtt_client = mqtt_client
        self._auth_state = auth_state or RfidAuthState(config.rfid.auth_window_seconds)
        self._reader = reader

    def start(self) -> None:
        if self._reader is None:
            logger.info("RFID auth module started without a card reader; waiting for hardware.")
            return

        self._reader.on_card(self.handle_card_uid)
        logger.info("RFID auth module started")

    def stop(self) -> None:
        if self._reader is not None:
            self._reader.close()
        logger.info("RFID auth module stopped")

    def handle_card_uid(self, card_uid: str) -> None:
        card = get_known_card(card_uid)
        timestamp = datetime.now(timezone.utc).isoformat()

        if card is None or not card.active:
            label = card.label if card is not None else "unknown"
            message = f"RFID card {card_uid} rejected"
            if card is not None and not card.active:
                message = f"RFID card {card_uid} ({label}) is disabled"

            create_event(
                Event(
                    node_id=config.node.node_id,
                    sensor=MODULE_ID,
                    status=STATUS_DENIED,
                    severity="warning",
                    message=message,
                )
            )
            self._publish_state(status="denied", card_uid=card_uid, card_label=label, timestamp=timestamp)
            return

        touch_known_card(card_uid)
        session = self._auth_state.authorize(
            card_uid=card_uid,
            card_label=card.label,
            window_seconds=config.rfid.auth_window_seconds,
        )

        create_event(
            Event(
                node_id=config.node.node_id,
                sensor=MODULE_ID,
                status=STATUS_AUTHORIZED,
                severity="info",
                message=f"RFID card {card_uid} ({card.label}) authenticated",
            )
        )
        self._publish_state(
            status="authorized",
            card_uid=card_uid,
            card_label=card.label,
            timestamp=timestamp,
            expires_at=session.expires_at,
        )

    def _publish_state(self, status: str, card_uid: str, card_label: str, timestamp: str, expires_at: str | None = None) -> None:
        payload = SensorStatePayload(
            sensor_id=SENSOR_ID,
            sensor_type="rfid",
            state=status,
            timestamp=timestamp,
            metadata={
                "card_uid": card_uid,
                "card_label": card_label,
                **({"expires_at": expires_at} if expires_at is not None else {}),
            },
        )
        topic = sensor_state_topic(config.node.node_id, SENSOR_ID)
        self._mqtt_client.publish(topic, payload.to_json(), retain=True)

