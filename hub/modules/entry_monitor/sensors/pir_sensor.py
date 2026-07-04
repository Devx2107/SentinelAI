"""PIR motion sensor driver.

Wraps GPIO Zero's MotionSensor class behind the BaseSensor interface,
so the entry_monitor module never imports gpiozero directly.
"""

from __future__ import annotations

import logging

from gpiozero import MotionSensor as GPIOZeroMotionSensor

from shared.base_sensor import BaseSensor, StateChangeCallback

logger = logging.getLogger(__name__)

MOTION = "motion"
CLEAR = "clear"


class PIRSensor(BaseSensor):
    """PIR motion sensor on a single GPIO pin."""

    sensor_type = "pir"

    def __init__(self, sensor_id: str, pin: int) -> None:
        self.sensor_id = sensor_id
        self._device = GPIOZeroMotionSensor(pin)
        self._callbacks: list[StateChangeCallback] = []

        self._device.when_motion = lambda: self._handle_change(MOTION)
        self._device.when_no_motion = lambda: self._handle_change(CLEAR)

    def read(self) -> str:
        return MOTION if self._device.motion_detected else CLEAR

    def on_change(self, callback: StateChangeCallback) -> None:
        self._callbacks.append(callback)

    def _handle_change(self, new_state: str) -> None:
        logger.debug("PIR '%s' state -> %s", self.sensor_id, new_state)
        for callback in self._callbacks:
            try:
                callback(new_state)
            except Exception:
                logger.exception("Error in PIR state-change callback")

    def close(self) -> None:
        self._device.close()
