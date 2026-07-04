"""Module loader.

Starts every registered BaseModule at hub startup and stops them
cleanly at shutdown. For Phase 1 this is an explicit registry rather
than filesystem auto-discovery — with only one real module built so
far, magic directory-scanning would add complexity without payoff.
As more modules come online (motion_monitor, environment, rfid_auth),
this is the one place that needs a new line added; nothing else in
the hub needs to change.
"""

from __future__ import annotations

import logging

from modules.base_module import BaseModule
from modules.entry_monitor.module import EntryMonitorModule

logger = logging.getLogger(__name__)


def build_modules(mqtt_client) -> list[BaseModule]:
    """Construct every module SentinelAI currently ships.

    Add new modules here as they're built. Each one only needs to
    implement BaseModule — the loader doesn't care about internals.
    """
    return [
        EntryMonitorModule(mqtt_client=mqtt_client),
        # Future: MotionMonitorModule(...), EnvironmentModule(...), RFIDAuthModule(...)
    ]


class ModuleLoader:
    """Starts and stops the full set of hub modules as a unit."""

    def __init__(self, mqtt_client) -> None:
        self._modules = build_modules(mqtt_client)

    def start_all(self) -> None:
        for module in self._modules:
            logger.info("Starting module '%s'", module.module_id)
            module.start()

    def stop_all(self) -> None:
        for module in self._modules:
            logger.info("Stopping module '%s'", module.module_id)
            try:
                module.stop()
            except Exception:
                logger.exception("Error stopping module '%s'", module.module_id)
