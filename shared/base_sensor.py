"""Abstract sensor interface.

Every physical sensor driver (PIR, ultrasonic, DHT11, RFID reader...)
implements this interface, whether it runs on the hub directly or on
a future RPi 0 W node agent. Business logic (modules) depends only on
this interface, never on GPIO Zero or any hardware library directly —
that's what makes swapping or adding sensors safe.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

StateChangeCallback = Callable[[str], None]


class BaseSensor(ABC):
    """Interface every sensor driver implements."""

    #: Unique identifier for this sensor instance, e.g. "pir_front_entry".
    sensor_id: str

    #: Category of sensor, e.g. "pir", "ultrasonic", "dht11".
    sensor_type: str

    @abstractmethod
    def read(self) -> str:
        """Return the sensor's current state as a string (e.g. "motion", "clear")."""
        raise NotImplementedError

    @abstractmethod
    def on_change(self, callback: StateChangeCallback) -> None:
        """Register a callback invoked with the new state whenever it changes."""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Release any hardware resources (GPIO pins, file handles, etc.)."""
        raise NotImplementedError
