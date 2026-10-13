"""Entry monitor module.

Phase 1 capability: when the PIR sensor detects motion, capture frames
from the Pi Camera and run person detection to confirm whether the
trigger was an actual person (reduces false positives from pets,
shadows, etc.). Every trigger produces an Event either way, with
different status/severity depending on whether a person was confirmed.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from config import config
from core.auth_state import RfidAuthState
from database.models.event import Event, create_event
from modules.base_module import BaseModule
from shared.mqtt_topics import sensor_state_topic
from shared.schemas import SensorStatePayload

logger = logging.getLogger(__name__)

MODULE_ID = "entry_monitor"
SENSOR_ID = "pir_front_entry"
MOTION = "motion"

STATUS_PERSON_CONFIRMED = "person_confirmed"
STATUS_MOTION_NO_PERSON = "motion_no_person"


class EntryMonitorModule(BaseModule):
    """PIR-triggered, camera-confirmed entry monitoring."""

    module_id = MODULE_ID

    def __init__(
        self,
        mqtt_client,
        auth_state: Optional[RfidAuthState] = None,
        pir=None,
        camera=None,
        detector=None,
    ) -> None:
        self._mqtt_client = mqtt_client
        self._auth_state = auth_state
        self._pir = pir
        self._camera = camera
        self._detector = detector

        if self._pir is None:
            try:
                from modules.entry_monitor.sensors.pir_sensor import PIRSensor
            except ModuleNotFoundError as exc:
                logger.warning(
                    "Skipping PIR setup because a hardware dependency is unavailable: %s",
                    exc,
                )
            else:
                try:
                    self._pir = PIRSensor(sensor_id=SENSOR_ID, pin=config.gpio.pir_pin)
                except Exception as exc:
                    logger.warning("Skipping PIR setup because it could not be initialized: %s", exc)

        if self._camera is None:
            try:
                from modules.entry_monitor.vision.frame_capture import FrameCapture
            except ModuleNotFoundError as exc:
                logger.warning(
                    "Skipping camera setup because a hardware dependency is unavailable: %s",
                    exc,
                )
            else:
                try:
                    self._camera = FrameCapture(resolution=config.vision.capture_resolution)
                except Exception as exc:
                    logger.warning("Skipping camera setup because it could not be initialized: %s", exc)

        if self._detector is None:
            try:
                from modules.entry_monitor.vision.detector import PersonDetector
            except ModuleNotFoundError as exc:
                logger.warning(
                    "Skipping vision detector setup because a hardware dependency is unavailable: %s",
                    exc,
                )
            else:
                try:
                    self._detector = PersonDetector()
                except Exception as exc:
                    logger.warning("Skipping vision detector setup because it could not be initialized: %s", exc)

    def start(self) -> None:
        if self._pir is None or self._camera is None or self._detector is None:
            logger.info(
                "Entry monitor module started in degraded mode; hardware dependencies are unavailable."
            )
            return

        self._camera.start()
        self._pir.on_change(self._on_pir_change)
        logger.info("Entry monitor module started (PIR on GPIO %s)", config.gpio.pir_pin)

    def stop(self) -> None:
        try:
            if self._pir is not None:
                self._pir.close()
                self._pir = None
        finally:
            if self._camera is not None:
                self._camera.stop()
                self._camera = None
        logger.info("Entry monitor module stopped")

    def _on_pir_change(self, state: str) -> None:
        if state != MOTION:
            return  # Only act on motion trigger, not the "clear" transition.

        logger.info("PIR triggered - capturing frames for person confirmation")
        confirmed, confidence = self._confirm_person()
        auth_active = self._auth_state is not None and self._auth_state.is_authorized()

        if confirmed:
            if auth_active:
                status = "person_confirmed_authenticated"
                severity = "info"
                message = (
                    f"Person confirmed at entry while RFID auth is active "
                    f"(confidence {confidence:.0%})"
                )
            else:
                status = STATUS_PERSON_CONFIRMED
                severity = "warning"
                message = f"Person confirmed at entry (confidence {confidence:.0%})"
        else:
            if auth_active:
                status = "motion_authenticated"
                severity = "info"
                message = "Motion detected while RFID auth is active; alert suppressed"
            else:
                status = STATUS_MOTION_NO_PERSON
                severity = "info"
                message = "Motion detected but no person confirmed by camera"

        self._log_event(status=status, severity=severity, message=message, confidence=confidence)
        self._publish_state(status=status, confidence=confidence)

    def _confirm_person(self) -> tuple[bool, float]:
        """Sample frames over the capture window, return the best detection found."""
        best_confidence = 0.0
        person_found = False

        samples = config.vision.frames_per_capture_window
        interval = config.vision.capture_window_seconds / max(samples, 1)

        for _ in range(samples):
            frame = self._camera.capture_frame()
            result = self._detector.detect_person(frame)
            best_confidence = max(best_confidence, result.confidence)
            if result.person_detected:
                person_found = True
                break
            time.sleep(interval)

        return person_found, best_confidence

    def _log_event(self, status: str, severity: str, message: str, confidence: float) -> None:
        create_event(
            Event(
                node_id=config.node.node_id,
                sensor=MODULE_ID,
                status=status,
                severity=severity,
                message=message,
                confidence=confidence,
            )
        )

    def _publish_state(self, status: str, confidence: float) -> None:
        payload = SensorStatePayload(
            sensor_id=SENSOR_ID,
            sensor_type="pir+vision",
            state=status,
            timestamp=datetime.now(timezone.utc).isoformat(),
            confidence=confidence,
        )
        topic = sensor_state_topic(config.node.node_id, SENSOR_ID)
        self._mqtt_client.publish(topic, payload.to_json())
