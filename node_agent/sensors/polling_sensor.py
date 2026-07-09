"""Polling-based BaseSensor helper for node agents."""

from __future__ import annotations

import logging
import threading
import time
from abc import abstractmethod
from typing import Optional

from shared.base_sensor import BaseSensor, StateChangeCallback

logger = logging.getLogger(__name__)


class PollingSensor(BaseSensor):
    """Base sensor that detects changes by polling `read()` on an interval."""

    poll_interval_seconds: float = 0.5
    _initial_state: Optional[str] = None

    def __init__(self, sensor_id: str) -> None:
        self.sensor_id = sensor_id
        self._callbacks: list[StateChangeCallback] = []
        self._stop_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None

    def on_change(self, callback: StateChangeCallback) -> None:
        self._callbacks.append(callback)
        if self._poll_thread is None:
            self._start_polling()

    def close(self) -> None:
        self._stop_event.set()
        if self._poll_thread is not None and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)

    def _start_polling(self) -> None:
        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self) -> None:
        previous_state = self._initial_state
        while not self._stop_event.is_set():
            current_state = self.read()
            if previous_state is None:
                previous_state = current_state
            elif current_state != previous_state:
                previous_state = current_state
                self._notify(current_state)
            time.sleep(self.poll_interval_seconds)

    def _notify(self, new_state: str) -> None:
        logger.debug("Sensor '%s' state -> %s", self.sensor_id, new_state)
        for callback in self._callbacks:
            try:
                callback(new_state)
            except Exception:
                logger.exception("Error in sensor state-change callback")

