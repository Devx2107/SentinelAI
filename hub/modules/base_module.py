"""Abstract base class every hub module implements.

This is the core "operating system" seam: the module loader discovers
and starts anything implementing this interface without needing to
know what sensors or logic live inside it. A future `rfid_auth` or
`gas_detector` module is "write a class implementing BaseModule",
never "modify the hub core".
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseModule(ABC):
    """Interface for a pluggable SentinelAI capability."""

    #: Unique, human-readable identifier for this module, e.g. "entry_monitor".
    module_id: str

    @abstractmethod
    def start(self) -> None:
        """Start the module: wire up sensors, subscribe to MQTT topics, etc.

        Called once by the module loader at hub startup. Must not block.
        """
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        """Cleanly shut down the module (release GPIO pins, camera, etc.)."""
        raise NotImplementedError
